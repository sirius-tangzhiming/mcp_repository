"""
房屋意图识别 MCP Server
从对话上下文中精确识别用户提到的房屋，返回 precinct_id + house_id + ys_ets_code

工具:
  - recognize_house: 核心意图识别（混合搜索 向量+BM25）
  - search_house: 语义搜索房屋（纯向量）
  - query_house_by_id: 按 house_id 精确查询
  - list_buildings: 列出项目的楼栋/单元结构
  - search_house_by_path: 按路径精确查找（多条件标量过滤）
"""

import os
import re
import requests
from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker
from mcp.server.fastmcp import FastMCP

# ============================== 配置 ==============================
MILVUS_URI = os.environ.get("MILVUS_URI", "http://10.15.208.159:19530")
COLLECTION_NAME = "house_intent"

OLLAMA_EMBEDDING_URL = os.environ.get("OLLAMA_EMBEDDING_URL", "http://10.15.208.159:11434/api/embed")
EMBEDDING_MODEL = "bge-m3:latest"
EMBEDDING_DIM = 1024
# ==================================================================

# ====================== 字段标签映射 ======================
FIELD_LABELS = {
    "house_id":         "房屋ID",
    "precinct_id":      "项目ID",
    "project_name":     "项目名称",
    "group_name":       "分期/组团",
    "building_name":    "栋",
    "unit_name":        "单元",
    "house_name":       "房号",
    "house_short_name": "房屋简称",
    "house_no":         "房屋编号",
    "charging_area":    "计费面积",
    "ys_ets_code":      "易软编码",
    "house_full_name":  "房屋全称",
}

# 搜索结果输出字段
SEARCH_OUTPUT_FIELDS = [
    "precinct_id", "project_name", "group_name",
    "building_name", "unit_name", "house_name",
    "house_short_name", "house_full_name",
    "house_id", "ys_ets_code",
]

# 所有标量字段
ALL_SCALAR_FIELDS = list(FIELD_LABELS.keys())
# ==================================================================

mcp = FastMCP("house-search", instructions="房屋意图识别服务，从自然语言中识别房屋，返回项目ID+房屋ID+易软编码")


def _get_client() -> MilvusClient:
    """获取 Milvus 客户端"""
    return MilvusClient(uri=MILVUS_URI)


def _generate_embedding(text: str) -> list[list[float]]:
    """生成单条文本的 embedding"""
    response = requests.post(
        OLLAMA_EMBEDDING_URL,
        json={"model": EMBEDDING_MODEL, "input": [text]},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def _format_house_result(hit: dict, idx: int) -> str:
    """格式化单条房屋搜索结果"""
    e = hit["entity"]
    return (
        f"{idx}. [{hit['distance']:.4f}] "
        f"{e.get('project_name', '')} | "
        f"{e.get('house_short_name', e.get('house_full_name', ''))} | "
        f"项目ID={e.get('precinct_id', '')} | "
        f"房屋ID={e.get('house_id', '')} | "
        f"易软编码={e.get('ys_ets_code', '')}"
    )


# ============================== 工具1: recognize_house ==============================
@mcp.tool()
def recognize_house(text: str, precinct_id: str = "", project_name: str = "",
                    limit: int = 10) -> str:
    """从自然语言文本中识别房屋。用户可能以全称、简称、缩写、房号等多种方式提到房屋，
    本工具通过混合搜索（向量语义+BM25关键词）精准匹配。

    当上下文中已知项目时，务必传入 precinct_id 或 project_name 以提高准确率。

    Args:
        text: 包含房屋信息的自然语言文本，如"博翠山5栋205"、"CQBCS-A-GC-5-1-0205"
        precinct_id: 项目ID，如已知则传入可大幅缩小搜索范围
        project_name: 项目名称，如已知则传入可缩小搜索范围
        limit: 返回结果数量，默认10
    """
    client = _get_client()
    query_embedding = _generate_embedding(text)

    # 向量搜索 — 多召回
    req_vec = AnnSearchRequest(
        data=query_embedding,
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"ef": 256}},
        limit=limit * 3,
    )

    # BM25 全文检索 — 多召回
    req_ft = AnnSearchRequest(
        data=[text],
        anns_field="sparse_embedding",
        param={"metric_type": "BM25"},
        limit=limit * 3,
    )

    # 构建过滤条件
    filters = []
    if precinct_id:
        filters.append(f'precinct_id == "{precinct_id}"')
    if project_name:
        filters.append(f'project_name == "{project_name}"')
    filter_expr = " and ".join(filters) if filters else ""

    kwargs = {
        "collection_name": COLLECTION_NAME,
        "reqs": [req_vec, req_ft],
        "ranker": RRFRanker(k=60),
        "limit": limit,
        "output_fields": SEARCH_OUTPUT_FIELDS,
    }
    if filter_expr:
        kwargs["filter"] = filter_expr

    results = client.hybrid_search(**kwargs)

    filter_desc = ""
    if precinct_id:
        filter_desc += f" 项目ID={precinct_id}"
    if project_name:
        filter_desc += f" 项目={project_name}"

    lines = [f"房屋识别: \"{text}\"{filter_desc} (返回{len(results[0])}条)\n"]
    for i, hit in enumerate(results[0]):
        lines.append(_format_house_result(hit, i + 1))
    return "\n".join(lines)


# ============================== 工具2: search_house ==============================
@mcp.tool()
def search_house(query: str, limit: int = 10) -> str:
    """语义搜索房屋。根据自然语言描述搜索房屋，适用于模糊描述场景。

    Args:
        query: 搜索文本，如"科技云城1栋"
        limit: 返回结果数量，默认10
    """
    client = _get_client()
    query_embedding = _generate_embedding(query)

    results = client.search(
        collection_name=COLLECTION_NAME,
        data=query_embedding,
        anns_field="embedding",
        limit=limit,
        output_fields=SEARCH_OUTPUT_FIELDS,
        search_params={"metric_type": "COSINE", "params": {"ef": 256}},
    )

    lines = [f"语义搜索: \"{query}\" (返回{len(results[0])}条)\n"]
    for i, hit in enumerate(results[0]):
        lines.append(_format_house_result(hit, i + 1))
    return "\n".join(lines)


# ============================== 工具3: query_house_by_id ==============================
@mcp.tool()
def query_house_by_id(house_id: str) -> str:
    """按房屋ID精确查询房屋详情。用于已知 house_id 需要获取完整信息的场景。

    Args:
        house_id: 房屋ID
    """
    client = _get_client()
    results = client.query(
        collection_name=COLLECTION_NAME,
        filter=f'house_id == "{house_id}"',
        output_fields=ALL_SCALAR_FIELDS,
    )

    if not results:
        return f"未找到房屋: house_id=\"{house_id}\""

    lines = [f"精确查询: house_id=\"{house_id}\" (找到{len(results)}条)\n"]
    for r in results:
        for field, label in FIELD_LABELS.items():
            lines.append(f"{label}: {r.get(field, '')}")
        lines.append("---")
    return "\n".join(lines)


# ============================== 工具4: list_buildings ==============================
@mcp.tool()
def list_buildings(precinct_id: str) -> str:
    """列出项目下的楼栋和单元结构。当搜索结果不明确时，可先列出楼栋供用户确认。

    Args:
        precinct_id: 项目ID
    """
    client = _get_client()
    results = client.query(
        collection_name=COLLECTION_NAME,
        filter=f'precinct_id == "{precinct_id}"',
        output_fields=["project_name", "building_name", "unit_name"],
        limit=16384,
    )

    if not results:
        return f"未找到项目: precinct_id=\"{precinct_id}\""

    # 按 building_name → unit_name 去重组织
    project_name = results[0].get("project_name", "")
    building_map: dict[str, set[str]] = {}
    for r in results:
        bld = r.get("building_name", "")
        unit = r.get("unit_name", "")
        if bld not in building_map:
            building_map[bld] = set()
        if unit:
            building_map[bld].add(unit)

    lines = [f"项目 {precinct_id} ({project_name}) 楼栋结构:\n"]
    for bld in sorted(building_map.keys()):
        units = ", ".join(sorted(building_map[bld]))
        lines.append(f"  {bld}: {units}" if units else f"  {bld}")
    lines.append(f"\n共 {len(building_map)} 栋")
    return "\n".join(lines)


# ============================== 工具5: search_house_by_path ==============================
@mcp.tool()
def search_house_by_path(precinct_id: str, building_name: str = "",
                         unit_name: str = "", house_name: str = "",
                         limit: int = 50) -> str:
    """按层级路径精确查找房屋。当用户提供了明确的项目+栋+单元+房号时可使用，
    比向量搜索更精确，适合结构化查询场景。

    Args:
        precinct_id: 项目ID（必填）
        building_name: 栋名，如"5栋"，留空不过滤
        unit_name: 单元名，如"1单元"，留空不过滤
        house_name: 房号，如"0205"，留空不过滤
        limit: 返回数量，默认50
    """
    client = _get_client()

    filters = [f'precinct_id == "{precinct_id}"']
    if building_name:
        filters.append(f'building_name == "{building_name}"')
    if unit_name:
        filters.append(f'unit_name == "{unit_name}"')
    if house_name:
        filters.append(f'house_name == "{house_name}"')
    filter_expr = " and ".join(filters)

    results = client.query(
        collection_name=COLLECTION_NAME,
        filter=filter_expr,
        output_fields=ALL_SCALAR_FIELDS,
        limit=limit,
    )

    if not results:
        return f"未找到匹配房屋: {filter_expr}"

    lines = [f"路径查询: {filter_expr} (找到{len(results)}条)\n"]
    for i, r in enumerate(results):
        lines.append(
            f"{i+1}. {r.get('project_name', '')} | "
            f"{r.get('house_short_name', '')} | "
            f"项目ID={r.get('precinct_id', '')} | "
            f"房屋ID={r.get('house_id', '')} | "
            f"易软编码={r.get('ys_ets_code', '')}"
        )
    return "\n".join(lines)


def main():
    """CLI 入口点"""
    mcp.run()


if __name__ == "__main__":
    main()