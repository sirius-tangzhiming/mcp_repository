"""
收费中心 MCP Server
封装收费中心 Java API，提供房屋信息查询、业主信息查询、欠费查询

工具:
  - query_house_info: 根据房屋ID精确查询房屋信息和业主信息
  - query_house_by_phone: 根据手机号查询业主房产信息（带签名验证）
  - get_owner_by_name: 根据业主姓名模糊查询业主信息
  - query_outstanding_fees: 查询房屋欠费明细

配置:
  所有敏感配置通过环境变量注入，不硬编码任何链接或密钥：
  - CHARGE_API_BASE: API基础地址（必填），如 
  - CHARGE_SIGN_SECRET: 签名密钥（必填），用于 listHouseInfoByPhone 接口
"""

import hashlib
import os

import requests
from mcp.server.fastmcp import FastMCP

# ============================== 配置 ==============================
# 所有链接和密钥均通过环境变量配置，不硬编码到代码中
API_BASE = os.environ.get("CHARGE_API_BASE", "")
SIGN_SECRET = os.environ.get("CHARGE_SIGN_SECRET", "")
SIGN_TYPE = "MD5"


def _check_config() -> str | None:
    """检查必填配置，返回错误信息或 None"""
    if not API_BASE:
        return "未配置 CHARGE_API_BASE 环境变量，请在启动时设置 API 基础地址"
    return None

def _generate_sign(params: dict) -> str:
    """根据查询参数生成 MD5 签名

    签名规则:
      1. 排除 sign 字段，过滤空值
      2. 按 key 字典升序排列
      3. 拼接 key1=value1&key2=value2&...&key=secret
      4. MD5 哈希后转大写
    """
    filtered = {k: v for k, v in params.items()
                if k != "sign" and v is not None and v != ""}
    sorted_keys = sorted(filtered.keys())
    string_a = "&".join(f"{k}={filtered[k]}" for k in sorted_keys)
    string_sign_temp = f"{string_a}&key={SIGN_SECRET}" if string_a else f"key={SIGN_SECRET}"

    if SIGN_TYPE == "MD5":
        return hashlib.md5(string_sign_temp.encode("utf-8")).hexdigest().upper()
    elif SIGN_TYPE == "HMACSHA256":
        import hmac
        return hmac.new(
            SIGN_SECRET.encode("utf-8"),
            string_sign_temp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()
    else:
        raise ValueError(f"不支持的签名类型: {SIGN_TYPE}")


def _format_owner_info(owner: dict) -> str:
    """格式化单条业主信息"""
    owner_property_map = {0: "业主", 1: "家属", 2: "租户", 3: "空置", 4: "家属"}
    prop_label = owner_property_map.get(owner.get("ownerProperty"), str(owner.get("ownerProperty", "")))
    return (
        f"    姓名: {owner.get('name', '')} | "
        f"业主ID: {owner.get('ownerId', '')} | "
        f"关系: {prop_label} | "
        f"电话: {owner.get('phone', '') or owner.get('mobile', '')}"
    )


def _format_house_info(house: dict, include_owner: bool = True) -> str:
    """格式化单条房屋信息"""
    lines = [
        f"  房屋ID: {house.get('houseId', '')} | "
        f"房屋EasyId: {house.get('houseEasyId', '')}",
        f"  房屋全称: {house.get('houseFullName', house.get('houseName', ''))}",
        f"  项目: {house.get('precinctName', '')} (ID={house.get('precinctId', '')})",
        f"  栋: {house.get('buildingName', '')} | "
        f"单元: {house.get('unitName', '')}",
    ]

    if include_owner and "relationOwnerInfoList" in house:
        owners = house["relationOwnerInfoList"]
        if owners:
            lines.append("  业主信息:")
            for o in owners:
                lines.append(_format_owner_info(o))
        else:
            lines.append("  业主信息: 无")

    return "\n".join(lines)


def _format_phone_house_info(item: dict) -> str:
    """格式化手机号查询返回的房屋信息"""
    owner_property_map = {"0": "业主", "1": "家属", "2": "租户", "3": "空置", "4": "家属"}
    prop_label = owner_property_map.get(str(item.get("ownerProperty", "")), str(item.get("ownerProperty", "")))

    lines = [
        f"  业主: {item.get('ownerName', '')} (ID={item.get('ownerId', '')}) | "
        f"关系: {prop_label} | 电话: {item.get('ownerPhone', '')}",
        f"  房屋: {item.get('houseFullName', item.get('houseName', ''))} | "
        f"房屋ID: {item.get('houseId', '')}",
        f"  项目: {item.get('precinctName', '')} (ID={item.get('precinctId', '')}) | "
        f"房屋类型: {item.get('houseType', '')}",
    ]
    if item.get("roomTypeName"):
        lines.append(f"  房间类型: {item['roomTypeName']}")
    if item.get("stageName"):
        lines.append(f"  阶段: {item['stageName']}")
    if item.get("chargingArea"):
        lines.append(f"  计费面积: {item['chargingArea']}")

    return "\n".join(lines)


def _format_fee_detail(fee: dict) -> str:
    """格式化单条欠费明细"""
    return (
        f"  {fee.get('chargeItemName', '')} | "
        f"金额: {fee.get('amount', 0)}元 | "
        f"周期: {fee.get('calcStartDate', '')}~{fee.get('calcEndDate', '')} | "
        f"账本: {fee.get('accountBook', '')} | "
        f"业主: {fee.get('ownerName', '')}(ID={fee.get('ownerId', '')})"
    )


# ==================================================================

mcp = FastMCP(
    "charge-center",
    instructions="收费中心服务，提供房屋信息查询、业主信息查询、欠费查询功能。"
    "所有 API 地址和密钥通过环境变量 CHARGE_API_BASE / CHARGE_SIGN_SECRET 配置。",
)


# ============================== 工具1: query_house_info ==============================
@mcp.tool()
def query_house_info(house_ids: list[int], house_easy_ids: list[str] | None = None,
                     return_owner_info: bool = True) -> str:
    """根据房屋ID精确查询房屋信息和业主信息。

    适用于已知房屋ID（houseId 或 houseEasyId），需要获取房屋详情和关联业主信息的场景。

    Args:
        house_ids: 房屋ID列表，如 [303822]，与 house_easy_ids 二选一
        house_easy_ids: 房屋EasyId列表（UUID格式），如 ["C0BE4E9C-..."]，可选
        return_owner_info: 是否返回业主信息，True 返回业主信息，False 仅返回房屋信息
    """
    err = _check_config()
    if err:
        return err

    payload = {
        "houseIds": house_ids,
        "houseEasyIds": house_easy_ids or [],
        "returnOwnerInfo": return_owner_info,
    }

    try:
        resp = requests.post(
            f"{API_BASE}/owner/listHouseInfoV2",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"请求失败: {e}"

    result = resp.json()
    if result.get("code") != 200:
        return f"接口返回错误: code={result.get('code')}, msg={result.get('msg', '')}"

    data = result.get("data", [])
    if not data:
        return f"未找到房屋信息: houseIds={house_ids}, houseEasyIds={house_easy_ids}"

    lines = [f"房屋信息查询 (返回{len(data)}条)\n"]
    for i, house in enumerate(data):
        lines.append(f"{i + 1}.")
        lines.append(_format_house_info(house, include_owner=return_owner_info))
        lines.append("")

    return "\n".join(lines)


# ============================== 工具2: query_house_by_phone ==============================
@mcp.tool()
def query_house_by_phone(phone: str) -> str:
    """根据手机号精确查询业主的房产信息。

    适用于已知业主手机号，需要查询其名下所有房产的场景。
    本接口需要签名验证，签名会自动生成。

    Args:
        phone: 业主手机号，如 "15223063562"
    """
    err = _check_config()
    if err:
        return err

    if not SIGN_SECRET:
        return "未配置 CHARGE_SIGN_SECRET 环境变量，手机号查询接口需要签名密钥"

    # 构造查询参数并生成签名
    params = {"phone": phone}
    sign = _generate_sign(params)
    params["sign"] = sign

    try:
        resp = requests.post(
            f"{API_BASE}/owner/listHouseInfoByPhone",
            params=params,
            json={},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"请求失败: {e}"

    result = resp.json()
    if result.get("code") != 200:
        return f"接口返回错误: code={result.get('code')}, msg={result.get('msg', '')}"

    data = result.get("data", [])
    if not data:
        return f"未找到手机号 {phone} 关联的房产信息"

    lines = [f"手机号查询: {phone} (返回{len(data)}条)\n"]
    for i, item in enumerate(data):
        lines.append(f"{i + 1}.")
        lines.append(_format_phone_house_info(item))
        lines.append("")

    return "\n".join(lines)


# ============================== 工具3: query_outstanding_fees ==============================
@mcp.tool()
def query_outstanding_fees(house_ids: list[int], precinct_id: str, owner_ids: list[int] | None = None,
                           charge_item_ids: list[int] | None = None) -> str:
    """查询房屋欠费明细。

    适用于已知房屋ID和业主ID，需要查看未缴费用明细的场景。

    Args:
        house_ids: 房屋ID列表，如 [303822]，必填
        owner_ids: 业主ID列表，如 [3670417]，可选，不传则查询该房屋所有欠费
        charge_item_ids: 科目ID列表，如 [17]，可选，不传则查询所有科目
        precinct_id: 项目ID，必填，从上下文中获取，如 "69579"
    """
    err = _check_config()
    if err:
        return err

    if not precinct_id:
        return "precinct_id（项目ID）为必填参数，请从上下文中获取"

    payload = {
        "houseIds": house_ids,
        "ownerIds": owner_ids or [],
        "chargeItemIds": charge_item_ids or [],
    }

    try:
        resp = requests.post(
            f"{API_BASE}/charge/tosPayment/detailsOfOutstandingHousingFees",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "precinctId": precinct_id,
            },
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"请求失败: {e}"

    result = resp.json()
    if result.get("code") != 200:
        return f"接口返回错误: code={result.get('code')}, msg={result.get('msg', '')}"

    data = result.get("data", [])
    if not data:
        return f"无欠费记录: houseIds={house_ids}, ownerIds={owner_ids}"

    # 按房屋分组
    house_map: dict[int, list] = {}
    for fee in data:
        hid = fee.get("houseId", 0)
        if hid not in house_map:
            house_map[hid] = []
        house_map[hid].append(fee)

    lines = [f"欠费查询 (共{len(data)}条记录，{len(house_map)}套房屋)\n"]
    for hid, fees in house_map.items():
        first = fees[0]
        total = sum(f.get("amount", 0) for f in fees)
        lines.append(f"房屋: {first.get('houseName', '')} (ID={hid})")
        lines.append(f"  业主: {first.get('ownerName', '')} (ID={first.get('ownerId', '')})")
        lines.append(f"  欠费合计: {total:.2f}元")
        lines.append("  明细:")
        for fee in fees:
            lines.append(_format_fee_detail(fee))
        lines.append("")

    return "\n".join(lines)


# ============================== 工具4: get_owner_by_name ==============================
@mcp.tool()
def get_owner_by_name(owner_name: str) -> str:
    """根据业主姓名查询业主信息。

    适用于已知业主姓名，需要查询业主ID和属性的场景。
    可能返回多条同名业主记录。

    Args:
        owner_name: 业主姓名，如 "张三"
    """
    err = _check_config()
    if err:
        return err

    try:
        resp = requests.post(
            f"{API_BASE}/owner/getOwnerInfoByName",
            json={"ownerName": owner_name},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"请求失败: {e}"

    result = resp.json()
    if result.get("code") != 200:
        return f"接口返回错误: code={result.get('code')}, msg={result.get('msg', '')}"

    data = result.get("data", [])
    if not data:
        return f"未找到业主: \"{owner_name}\""

    lines = [f"业主查询: \"{owner_name}\" (返回{len(data)}条)\n"]
    for i, owner in enumerate(data):
        phones = owner.get("phones", [])
        phone_str = ", ".join(phones) if phones else "无"
        lines.append(
            f"{i + 1}. 姓名: {owner.get('ownerName', '')} | "
            f"业主ID: {owner.get('ownerId', '')} | "
            f"属性: {owner.get('ownerProperty', '')} | "
            f"电话: {phone_str}"
        )

    return "\n".join(lines)


def main():
    """CLI 入口点"""
    mcp.run()


if __name__ == "__main__":
    main()
