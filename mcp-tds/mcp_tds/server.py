"""
TDS房产信息大屏 MCP Server
封装TDS Java API，提供户位信息、流转分析、缴费变动等查询

工具:
  - get_house_stages: 查询户房态列表
  - get_household_info: 查询户位信息
  - get_household_flow_history: 查询户位流转信息
  - get_occupancy_status_chart: 查询房态信息图表
  - get_area_ranking: 查询区域排行
  - list_payment_change_warnings: 查询缴费习惯即将改变户位预警
  - analysis_no_arrears: 不欠费客户分析
  - analysis_escape: 逃逸客户分析
  - analysis_long_arrears: 长期欠费客户分析
  - search_payment_patterns: 获取客户户位变化明细

配置:
  - TDS_API_BASE: API基础地址（必填，通过环境变量注入）
"""

import os
from datetime import datetime
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

# ============================== 配置 ==============================
API_BASE = os.environ.get("TDS_API_BASE", "")



def _check_config() -> str | None:
    """检查必填配置"""
    if not API_BASE:
        return "未配置 TDS_API_BASE 环境变量，请在启动时设置 API 基础地址"
    return None


def _get_headers() -> dict[str, str]:
    """构建通用请求头"""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "account-type": "-1",
        "data-date": today,
        "group-account": "true",
        "tds-level": "999",
    }


def _build_body(project_id: int, page_number: int = 1, page_size: int = 5000) -> dict[str, Any]:
    """构建通用请求体：时间按当前年份写死，只传项目ID"""
    year = datetime.now().year
    return {
        "areaCompanyIds": [],
        "cityCompanyIds": [],
        "startMonth": f"{year}-01-31",
        "endMonth": f"{year}-12-31",
        "houseStages": [],
        "projectIds": [project_id],
        "projectTypes": [],
        "stewardIds": [],
        "pageNumber": page_number,
        "pageSize": page_size,
    }


def _post(endpoint: str, project_id: int, page_number: int = 1, page_size: int = 5000) -> dict | str:
    """通用 POST 请求"""
    err = _check_config()
    if err:
        return err

    try:
        resp = requests.post(
            f"{API_BASE}{endpoint}",
            json=_build_body(project_id, page_number, page_size),
            headers=_get_headers(),
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"请求失败: {e}"

    result = resp.json()
    if result.get("code") != 0:
        return f"接口返回错误: code={result.get('code')}, msg={result.get('msg', '')}"

    return result.get("data", {})


def _get(endpoint: str) -> dict | str:
    """通用 GET 请求"""
    err = _check_config()
    if err:
        return err

    try:
        resp = requests.get(
            f"{API_BASE}{endpoint}",
            headers=_get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"请求失败: {e}"

    result = resp.json()
    if result.get("code") != 0:
        return f"接口返回错误: code={result.get('code')}, msg={result.get('msg', '')}"

    return result.get("data", [])


# ============================== 格式化函数 ==============================

def _fmt_household_info(data: dict) -> str:
    """格式化户位信息"""
    lines = ["户位信息:\n"]
    # 起始
    lines.append(f"  起始: 总数={data.get('startTotalCount',0)} | "
                 f"入住={data.get('startRuZCount',0)} | "
                 f"空关={data.get('startKongGCount',0)} | "
                 f"未领={data.get('startWeiLCount',0)} | "
                 f"空置={data.get('startKongZCount',0)}")
    # 终点
    lines.append(f"  终点: 总数={data.get('endTotalCount',0)} | "
                 f"入住={data.get('endRuZCount',0)} | "
                 f"空关={data.get('endKongGCount',0)} | "
                 f"未领={data.get('endWeiLCount',0)} | "
                 f"空置={data.get('endKongZCount',0)}")
    lines.append(f"  入住率: {data.get('checkInRate',0)}% | 已售率: {data.get('saleRate',0)}%")
    return "\n".join(lines)


def _fmt_flow_history(data: dict) -> str:
    """格式化户位流转信息"""
    lines = ["户位流转信息:\n"]

    # 不欠费
    lines.append("【不欠费】")
    lines.append(f"  起点={data.get('normalBasePointCount',0)} | 终点={data.get('normalRetentionCount',0)} | "
                 f"预存余额={data.get('normalPrepaidBalance',0)}")
    lines.append(f"  流入={data.get('normalInCount',0)}(同比{data.get('normalInRate',0)}%) | "
                 f"流出={data.get('normalOutCount',0)}(同比{data.get('normalOutRate',0)}%) | "
                 f"净流入={data.get('normalNetInflow',0)}")
    lines.append(f"  →逃逸: 速度={data.get('normalToEscapeSpeed',0)} 金额={data.get('normalToEscapeAmount',0)} "
                 f"户数={data.get('normalToEscapeInCount',0)}(同比{data.get('normalToEscapeInRate',0)}%)")
    lines.append(f"  →长期欠费: 速度={data.get('normalToLongArrearsSpeed',0)} 金额={data.get('normalToLongArrearsAmount',0)} "
                 f"户数={data.get('normalToLongArrearsInCount',0)}(同比{data.get('normalToLongArrearsInRate',0)}%)")

    # 逃逸
    lines.append("\n【逃逸】")
    lines.append(f"  基点={data.get('escapeBasePointCount',0)} | 留存={data.get('escapeRetentionCount',0)} | "
                 f"欠费金额={data.get('escapePrepaidBalance',0)}")
    lines.append(f"  流入={data.get('escapeInCount',0)}(同比{data.get('escapeInRate',0)}%) | "
                 f"流出={data.get('escapeOutCount',0)}(同比{data.get('escapeOutRate',0)}%) | "
                 f"净流入={data.get('escapeNetInflow',0)}")
    lines.append(f"  →不欠费: 速度={data.get('escapeToNormalSpeed',0)} 金额={data.get('escapeToNormalAmount',0)} "
                 f"户数={data.get('escapeToNormalInCount',0)}(同比{data.get('escapeToNormalInRate',0)}%)")
    lines.append(f"  →长期欠费: 速度={data.get('escapeToLongArrearsSpeed',0)} 金额={data.get('escapeToLongArrearsAmount',0)} "
                 f"户数={data.get('escapeToLongArrearsInCount',0)}(同比{data.get('escapeToLongArrearsInRate',0)}%)")

    # 长期欠费
    lines.append("\n【长期欠费】")
    lines.append(f"  基点={data.get('longArrearsBasePointCount',0)} | 留存={data.get('longArrearsRetentionCount',0)} | "
                 f"欠费金额={data.get('longArrearsAmount',0)}")
    lines.append(f"  流入={data.get('longArrearsInCount',0)}(同比{data.get('longArrearsInRate',0)}%) | "
                 f"流出={data.get('longArrearsOutCount',0)}(同比{data.get('longArrearsOutRate',0)}%) | "
                 f"净流入={data.get('longNetInflow',0)}")
    lines.append(f"  →不欠费: 速度={data.get('longArrearsToNormalSpeed',0)} 金额={data.get('longArrearsToNormalAmount',0)} "
                 f"户数={data.get('longArrearsToNormalInCount',0)}(同比{data.get('longArrearsToNormalInRate',0)}%)")
    lines.append(f"  →逃逸: 速度={data.get('longArrearsToEscapeSpeed',0)} 金额={data.get('longArrearsToEscapeAmount',0)} "
                 f"户数={data.get('longArrearsToEscapeInCount',0)}(同比{data.get('longArrearsToEscapeInRate',0)}%)")

    return "\n".join(lines)


def _fmt_status_chart(data: dict) -> str:
    """格式化房态信息图表"""
    lines = ["房态信息图表:\n"]

    for category, label, in_avg, out_avg in [
        ("normalCustomerCount", "不欠费", "normalInflowAvgCount", "normalOutflowAvgCount"),
        ("escapeCustomerCount", "逃逸", "escapeInflowAvgCount", "escapeOutflowAvgCount"),
        ("longArrearsCustomerCount", "长期欠费", "longArrearsInflowAvgCount", "longArrearsOutflowAvgCount"),
    ]:
        items = data.get(category, [])
        lines.append(f"【{label}】流入均值={data.get(in_avg,0)} 流出均值={data.get(out_avg,0)}")
        for item in items:
            lines.append(
                f"  {item.get('month','')}: 留存={item.get('retentionCount',0)} | "
                f"流入={item.get('inflowCount',0)} | 流出={item.get('outflowCount',0)} | "
                f"金额={item.get('amount',0)} | "
                f"流入速度={item.get('inflowSpeed',0)} | 流出速度={item.get('outflowSpeed',0)}"
            )
        lines.append("")

    return "\n".join(lines)


def _fmt_area_ranking(data: dict) -> str:
    """格式化区域排行"""
    records = data.get("records", [])
    type_map = {1: "区域", 2: "片区", 3: "项目"}

    lines = [f"区域排行 (共{data.get('total',0)}条):\n"]
    for r in records:
        t = type_map.get(r.get("type", 0), str(r.get("type", "")))
        lines.append(
            f"  [{t}] {r.get('name','')} (ID={r.get('id','')}): "
            f"不欠费={r.get('normalCount',0)} | 流失速度={r.get('lossSpeed',0)} | "
            f"同比={r.get('yearOnYearSpeed',0)} | 长期欠费={r.get('longArrearsCount',0)} | "
            f"去化速度={r.get('digestionSpeed',0)}"
        )
    return "\n".join(lines)


def _fmt_payment_warnings(data: dict) -> str:
    """格式化缴费习惯改变预警"""
    records = data.get("records", [])
    type_map = {1: "区域", 2: "片区", 3: "项目"}

    lines = [f"缴费习惯改变预警 (共{data.get('total',0)}条):\n"]
    for r in records:
        t = type_map.get(r.get("type", 0), str(r.get("type", "")))
        lines.append(
            f"  [{t}] {r.get('name','')} (ID={r.get('id','')}): "
            f"不欠费={r.get('normalCount',0)}(临界={r.get('normalCriticalCount',0)}) | "
            f"逃逸={r.get('escapeCount',0)}(临界={r.get('escapeCriticalCount',0)}) | "
            f"长期欠费={r.get('longArrearsCount',0)}(临界={r.get('longArrearsCriticalCount',0)})"
        )
    return "\n".join(lines)


def _fmt_customer_analysis(data: list, title: str) -> str:
    """格式化客户分析"""
    lines = [f"{title}:\n"]

    for item in data:
        area_name = item.get("areaName", "")
        group_name = item.get("groupName", "")
        lines.append(f"  区域: {area_name} | 分组: {group_name}")

        for detail_key, detail_label in [
            ("oneCustomerAnalysisDetail", "一级"),
            ("twoCustomerAnalysisDetail", "二级"),
            ("threeCustomerAnalysisDetail", "三级"),
        ]:
            detail = item.get(detail_key)
            if not detail:
                continue
            lines.append(f"    【{detail_label}】类型={detail.get('type','')} | "
                         f"总户位={detail.get('totalQuantity',0)} | "
                         f"基点={detail.get('startPoint',0)}(金额={detail.get('startPointAmount',0)}) | "
                         f"终点={detail.get('endPoint',0)}(金额={detail.get('endPointAmount',0)})")

            analysis = detail.get("customerAnalysisDetail", {})
            for shift_name, shift_data in analysis.items():
                lines.append(f"      {shift_name}: "
                             f"预存={shift_data.get('preStoredCustomers',0)} | "
                             f"非预存={shift_data.get('noPreStoredCustomers',0)} | "
                             f"3月内={shift_data.get('aging3',0)} | "
                             f"4-6月={shift_data.get('aging46',0)} | "
                             f"7-9月={shift_data.get('aging79',0)} | "
                             f"10-12月={shift_data.get('aging1012',0)} | "
                             f"13-24月={shift_data.get('aging1324',0)} | "
                             f"25月+={shift_data.get('aging25',0)} | "
                             f"预存余额={shift_data.get('preDepositBalance',0)} | "
                             f"欠费余额={shift_data.get('arrearsBalance',0)}")
        lines.append("")

    return "\n".join(lines)


def _fmt_payment_patterns(data: dict) -> str:
    """格式化客户户位变化明细"""
    records = data.get("records", [])
    shift_order = {"流失": 0, "滑档": 1, "去化": 2, "逃选": 3, "存续": 4, "改善": 5}
    records.sort(key=lambda r: (shift_order.get(r.get("shiftType", ""), 9), r.get("houseName", "")))

    from collections import Counter
    shift_stat = Counter(r.get("shiftType", "") for r in records)

    lines = [f"客户户位变化明细 (共{len(records)}条):\n"]
    lines.append("变动统计: " + " | ".join(f"{k}:{v}条" for k, v in sorted(shift_stat.items(), key=lambda x: shift_order.get(x[0], 9))))
    lines.append("")

    for r in records:
        iv = r.get("intervalVariation", {})
        months_str = " → ".join(iv.get(k, "") for k in sorted(iv.keys())) if iv else ""
        lines.append(
            f"  {r.get('butlerName','') or '未分配'} | "
            f"{r.get('houseName','')} | "
            f"{r.get('basePointType','')}({r.get('basePointAmount',0)}) → "
            f"{r.get('endType','')}({r.get('endAmount',0)}) | "
            f"{r.get('shiftType','')} | 月度: {months_str}"
        )

    return "\n".join(lines)


# ==================================================================

mcp = FastMCP(
    "tds",
    instructions="TDS房产信息大屏服务，提供户位信息、流转分析、缴费变动等查询。"
    "API 基础地址通过环境变量 TDS_API_BASE 配置。"
    "时间范围自动取当年1-12月，只需传入项目ID即可查询。",
)


# ============================== 工具1: get_house_stages ==============================
@mcp.tool()
def get_house_stages() -> str:
    """查询户房态列表。返回所有可选的房态类型。

    无需参数，返回房态枚举值列表。
    """
    result = _get("/tds/getHouseStagesList")
    if isinstance(result, str):
        return result

    if not result:
        return "未查询到房态列表"

    lines = [f"户房态列表 (共{len(result)}种):\n"]
    for i, stage in enumerate(result, 1):
        lines.append(f"  {i}. {stage}")
    return "\n".join(lines)


# ============================== 工具2: get_household_info ==============================
@mcp.tool()
def get_household_info(project_id: int) -> str:
    """查询户位信息。返回项目入住率、已售率及户位分布（入住/空关/未领/空置）。

    Args:
        project_id: 项目ID，如 409066
    """
    result = _post("/tos-tds/tds/getHouseholdInfo", project_id)
    if isinstance(result, str):
        return result
    return _fmt_household_info(result)


# ============================== 工具3: get_household_flow_history ==============================
@mcp.tool()
def get_household_flow_history(project_id: int) -> str:
    """查询户位流转信息。返回不欠费/逃逸/长期欠费三类客户的流入流出、同比、净流入等详细数据。

    Args:
        project_id: 项目ID，如 409066
    """
    result = _post("/tos-tds/tds/getHouseholdFlowHistory", project_id)
    if isinstance(result, str):
        return result
    return _fmt_flow_history(result)


# ============================== 工具4: get_occupancy_status_chart ==============================
@mcp.tool()
def get_occupancy_status_chart(project_id: int) -> str:
    """查询房态信息图表。返回不欠费/逃逸/长期欠费三类客户按月的留存、流入、流出、金额趋势数据。

    Args:
        project_id: 项目ID，如 409066
    """
    result = _post("/tos-tds/tds/getOccupancyStatusChart", project_id)
    if isinstance(result, str):
        return result
    return _fmt_status_chart(result)


# ============================== 工具5: get_area_ranking ==============================
@mcp.tool()
def get_area_ranking(project_id: int, page_number: int = 1, page_size: int = 50) -> str:
    """查询区域排行。返回项目下各区域的流失速度、去化速度、同比等排名数据。

    Args:
        project_id: 项目ID，如 409066
        page_number: 页码，默认1
        page_size: 每页条数，默认50
    """
    result = _post("/tos-tds/tds/getAreaRanking", project_id, page_number, page_size)
    if isinstance(result, str):
        return result
    return _fmt_area_ranking(result)


# ============================== 工具6: list_payment_change_warnings ==============================
@mcp.tool()
def list_payment_change_warnings(project_id: int, page_number: int = 1, page_size: int = 50) -> str:
    """查询缴费习惯即将改变户位预警。返回各区域/片区的不欠费、逃逸、长期欠费临界户数。

    Args:
        project_id: 项目ID，如 409066
        page_number: 页码，默认1
        page_size: 每页条数，默认50
    """
    result = _post("/tos-tds/tds/listHouseholdPaymentChangeWarnings", project_id, page_number, page_size)
    if isinstance(result, str):
        return result
    return _fmt_payment_warnings(result)


# ============================== 工具7: analysis_no_arrears ==============================
@mcp.tool()
def analysis_no_arrears(project_id: int) -> str:
    """不欠费客户分析。返回项目不欠费客户的预存/非预存、各账龄段分布及变动类型明细。

    Args:
        project_id: 项目ID，如 409066
    """
    result = _post("/tos-tds/tds/analysisNoArrears", project_id)
    if isinstance(result, str):
        return result
    return _fmt_customer_analysis(result, "不欠费客户分析")


# ============================== 工具8: analysis_escape ==============================
@mcp.tool()
def analysis_escape(project_id: int) -> str:
    """逃逸客户分析。返回项目逃逸客户的预存/非预存、各账龄段分布及变动类型明细。

    Args:
        project_id: 项目ID，如 409066
    """
    result = _post("/tos-tds/tds/analysisEscape", project_id)
    if isinstance(result, str):
        return result
    return _fmt_customer_analysis(result, "逃逸客户分析")


# ============================== 工具9: analysis_long_arrears ==============================
@mcp.tool()
def analysis_long_arrears(project_id: int) -> str:
    """长期欠费客户分析。返回项目长期欠费客户的预存/非预存、各账龄段分布及变动类型明细。

    Args:
        project_id: 项目ID，如 409066
    """
    result = _post("/tos-tds/tds/analysisLongArrears", project_id)
    if isinstance(result, str):
        return result
    return _fmt_customer_analysis(result, "长期欠费客户分析")


# ============================== 工具10: search_payment_patterns ==============================
@mcp.tool()
def search_payment_patterns(project_id: int, page_number: int = 1, page_size: int = 5000) -> str:
    """获取客户户位变化明细。返回每户的管家、房屋、基准/末位区间和金额、变动类型、月度区间变化轨迹。

    Args:
        project_id: 项目ID，如 409066
        page_number: 页码，默认1
        page_size: 每页条数，默认5000
    """
    result = _post("/tos-tds/tds/searchForChangesHousingPaymentPatternsList", project_id, page_number, page_size)
    if isinstance(result, str):
        return result
    return _fmt_payment_patterns(result)


def main():
    """CLI 入口点"""
    mcp.run()


if __name__ == "__main__":
    main()