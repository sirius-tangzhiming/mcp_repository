---
name: charge-query
description: 指导 AI 正确编排收费中心 MCP 服务的工具调用流程。当用户查询业主信息、房屋信息、欠费情况时自动应用。关键词：业主、房屋、欠费、物业费、手机号、业主姓名、房产查询。
---

# 收费中心查询编排

指导 AI 根据用户输入的类型，按正确顺序调用 MCP 工具链。

## 涉及的 MCP 服务

| 服务 | 工具 | 用途 |
|------|------|------|
| charge-center | `get_owner_by_name` | 按姓名查业主 |
| charge-center | `query_house_by_phone` | 按手机号查房产（自动签名） |
| charge-center | `query_house_info` | 按 houseId 查房屋+业主详情 |
| charge-center | `query_outstanding_fees` | 查欠费明细 |
| house-search | `recognize_house` / `search_house` | 自然语言识别房屋 |

## 核心原则

**precinctId 是查欠费的前提条件**，必须从前序工具的返回结果中获取，不能硬编码或猜测。

---

## 流程1：按业主姓名查询

触发：用户提到业主姓名（如"查一下张三的欠费"）

```
1. get_owner_by_name(owner_name="张三")
   → 获得 ownerId（可能多条同名记录，需确认）

2. 此时只有 ownerId，没有 houseId，需要结合其他信息：
   - 如有手机号 → 走流程2
   - 如有房屋描述 → 走流程3
   - 如只有姓名 → 告知用户需要更多信息（手机号或房屋地址）
```

**注意**：`get_owner_by_name` 只返回 ownerId 和属性，不返回关联房屋。拿到 ownerId 后仍需手机号或房屋信息才能继续查。

## 流程2：按手机号查询（最完整）

触发：用户提到手机号（如"17784322901的欠费"）

```
1. query_house_by_phone(phone="17784322901")
   → 获得 precinctId、houseId、ownerId、房屋全称等

2. 如需查欠费：
   query_outstanding_fees(
     house_ids=[<step1的houseId>],
     precinct_id="<step1的precinctId>",
     owner_ids=[<step1的ownerId>]
   )

3. 如需房屋详情：
   query_house_info(house_ids=[<houseId>], return_owner_info=True)
```

## 流程3：按房屋描述查询

触发：用户用自然语言描述房屋（如"博翠山5栋205的欠费"）

```
1. recognize_house(text="博翠山5栋205")
   → 获得 houseId、precinctId

2. query_house_info(house_ids=[<houseId>], return_owner_info=True)
   → 获得房屋详情 + 业主信息（ownerId、姓名、电话）

3. 如需查欠费：
   query_outstanding_fees(
     house_ids=[<houseId>],
     precinct_id="<precinctId>",
     owner_ids=[<ownerId>]   ← 从 step2 的业主信息中获取
   )
```

## 流程4：综合查询

触发：用户同时提供多种信息

**优先使用手机号**（信息最完整，一次调用即可获取所有 ID），其次用房屋描述，最后用姓名。

---

## 关键提醒

- `precinctId` 是 `query_outstanding_fees` 的**必填参数**，必须从上一步结果中获取
- `query_house_by_phone` 的签名是自动生成的，无需手动处理
- `get_owner_by_name` 可能返回同名多人，需向用户确认是哪一位
- 查欠费时建议传入 `owner_ids`，否则会返回该房屋所有业主的欠费
- 多套房产时，对每套分别调用 `query_outstanding_fees`（precinctId 可能不同）

## 返回结果格式化

向用户呈现时：
1. 先列出业主基本信息
2. 再列出关联房产
3. 最后列出欠费明细及合计金额
4. 如无欠费，明确告知"无欠费"
