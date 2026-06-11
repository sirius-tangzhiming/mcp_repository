"""
项目搜索 MCP Server
提供项目语义搜索、混合搜索、标量查询功能

字段映射说明：Milvus 不支持中文/特殊字符作为字段名，
因此 Excel 中文列名映射为英文字段名，详见 COLUMN_LABELS
"""

import os
import requests
from pymilvus import MilvusClient, DataType, AnnSearchRequest, RRFRanker
from mcp.server.fastmcp import FastMCP

# ============================== 配置 ==============================
MILVUS_URI = os.environ.get("MILVUS_URI", "")
COLLECTION_NAME = "monthly_project"

OLLAMA_EMBEDDING_URL = os.environ.get("OLLAMA_EMBEDDING_URL", "")
EMBEDDING_MODEL = "bge-m3:latest"
EMBEDDING_DIM = 1024
# ==================================================================

# ====================== Milvus 字段名 → 中文标签映射 ======================
COLUMN_LABELS = {
    "daguuanjia_project_id":  "大管家项目id",
    "project_name":           "项目名称",
    "daguuanjia_parent_id":   "大管家父项目id",
    "charge_project_id":      "收费系统项目id",
    "charge_parent_id":       "收费系统父项目id",
    "yiruan_project_id":      "易软项目id",
    "approval_code":          "项目立项编码",
    "org_id":                 "项目中台组织ID",
    "service_team":           "服务接管团队",
    "province":               "所属省份/直辖市",
    "city":                   "所属地级市",
    "address":                "地址",
    "project_status":         "项目状态",
    "type_level":             "层级",
    "enable_flag":            "项目启用/禁用",
}

# 搜索结果输出字段
SEARCH_OUTPUT_FIELDS = [
    "project_name", "province", "city",
    "address", "project_status", "service_team", "type_level",
]
# ==================================================================

mcp = FastMCP("project-search", instructions="项目搜索服务，支持语义搜索、混合搜索（向量+BM25关键词）和标量精确查询")


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


def _format_search_result(hit: dict, idx: int) -> str:
    """格式化单条搜索结果"""
    e = hit["entity"]
    return (
        f"{idx}. [{hit['distance']:.4f}] "
        f"{e.get('project_name', '')} | "
        f"{e.get('province', '')}{e.get('city', '')} | "
        f"{e.get('address', '')[:60]} | "
        f"状态:{e.get('project_status', '')} | "
        f"{e.get('service_team', '')}"
    )


@mcp.tool()
def search_project(query: str, limit: int = 10) -> str:
    """语义搜索项目。根据自然语言描述搜索项目，例如"重庆住宅项目"、"滨江花园"。

    Args:
        query: 搜索文本，如项目名、地址关键词等
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
        search_params={"metric_type": "COSINE", "params": {"ef": 128}},
    )

    lines = [f"语义搜索: \"{query}\" (返回{len(results[0])}条)\n"]
    for i, hit in enumerate(results[0]):
        lines.append(_format_search_result(hit, i + 1))
    return "\n".join(lines)


@mcp.tool()
def hybrid_search_project(query: str, limit: int = 10, province: str = "", city: str = "") -> str:
    """混合搜索项目（向量语义 + BM25关键词）。对口语化短关键词效果更好，如"10年城"、"廊桥"。

    Args:
        query: 搜索文本，支持口语化关键词
        limit: 返回结果数量，默认10
        province: 所属省份/直辖市，如"重庆市"，留空不过滤
        city: 所属地级市，如"成都市"，留空不过滤
    """
    client = _get_client()
    query_embedding = _generate_embedding(query)

    req_vec = AnnSearchRequest(
        data=query_embedding,
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=limit,
    )
    req_ft = AnnSearchRequest(
        data=[query],
        anns_field="sparse_embedding",
        param={"metric_type": "BM25"},
        limit=limit,
    )

    # 构建过滤条件
    filters = []
    if province:
        filters.append(f'province == "{province}"')
    if city:
        filters.append(f'city == "{city}"')
    filter_expr = " and ".join(filters)

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

    filter_desc = f" | 过滤: {filter_expr}" if filter_expr else ""
    lines = [f"混合搜索(向量+BM25): \"{query}\"{filter_desc} (返回{len(results[0])}条)\n"]
    for i, hit in enumerate(results[0]):
        lines.append(_format_search_result(hit, i + 1))
    return "\n".join(lines)


@mcp.tool()
def query_project_by_name(name: str) -> str:
    """按项目名称精确查询项目详情。用于已知项目名需要获取其详细信息。

    Args:
        name: 项目名称（精确匹配），如"重庆10年城"
    """
    client = _get_client()
    all_fields = list(COLUMN_LABELS.keys())
    results = client.query(
        collection_name=COLLECTION_NAME,
        filter=f'project_name == "{name}"',
        output_fields=all_fields,
    )

    if not results:
        return f"未找到项目: \"{name}\""

    lines = [f"精确查询: \"{name}\" (找到{len(results)}条)\n"]
    for r in results:
        for field, label in COLUMN_LABELS.items():
            lines.append(f"{label}: {r.get(field, '')}")
        lines.append("---")
    return "\n".join(lines)


@mcp.tool()
def query_projects_by_filter(province: str = "", city: str = "",
                              status: str = "", service_team: str = "",
                              type_level: str = "", enable_flag: str = "",
                              limit: int = 20) -> str:
    """按标量字段过滤查询项目列表。用于按省份、城市、状态等条件筛选项目。

    Args:
        province: 所属省份/直辖市，如"重庆市"
        city: 所属地级市，如"成都市"
        status: 项目状态，如"entered"、"quited"、"waiting_quit"
        service_team: 服务接管团队，如"residentialServices"、"governmentEnterpriseServices"
        type_level: 层级，1-集团，2-区域，3-城区，4-项目
        enable_flag: 项目启用/禁用，"Y"或"N"
        limit: 返回数量，默认20
    """
    client = _get_client()

    filters = []
    if province:
        filters.append(f'province == "{province}"')
    if city:
        filters.append(f'city == "{city}"')
    if status:
        filters.append(f'project_status == "{status}"')
    if service_team:
        filters.append(f'service_team == "{service_team}"')
    if type_level:
        filters.append(f'type_level == "{type_level}"')
    if enable_flag:
        filters.append(f'enable_flag == "{enable_flag}"')

    if not filters:
        return "请至少提供一个过滤条件"

    filter_expr = " and ".join(filters)

    results = client.query(
        collection_name=COLLECTION_NAME,
        filter=filter_expr,
        output_fields=[
            "daguuanjia_project_id", "project_name",
            "province", "city", "address",
            "project_status", "service_team", "enable_flag",
        ],
        limit=limit,
    )

    lines = [f"过滤查询: {filter_expr} (找到{len(results)}条)\n"]
    for i, r in enumerate(results):
        lines.append(
            f"{i+1}. {r['project_name']} | "
            f"{r['province']}{r['city']} | {r['address'][:50]} | "
            f"状态:{r['project_status']} | {r['service_team']} | "
            f"启用:{r['enable_flag']}"
        )
    return "\n".join(lines)


def main():
    """CLI 入口点"""
    mcp.run()


if __name__ == "__main__":
    main()