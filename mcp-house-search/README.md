# mcp-house-search

房屋意图识别 MCP Server，基于 Milvus 向量数据库，从自然语言中识别用户提到的房屋，返回项目ID + 房屋ID + 易软编码。

## 功能

| 工具 | 说明 |
|---|---|
| `recognize_house` | 核心工具：从自然语言识别房屋（混合搜索 向量+BM25） |
| `search_house` | 语义搜索房屋（纯向量） |
| `query_house_by_id` | 按 house_id 精确查询 |
| `list_buildings` | 列出项目的楼栋/单元结构 |
| `search_house_by_path` | 按路径精确查找（项目+栋+单元+房号） |

## 环境变量


## 安装

```bash
pip install git+https://github.com/sirius-tangzhiming/mcp_-repository.git#subdirectory=mcp-house-search
```

## MCP 客户端配置

```json
{
  "mcpServers": {
    "house-search": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/sirius-tangzhiming/mcp_-repository.git#subdirectory=mcp-house-search",
        "mcp-house-search"
      ],
      "env": {
        "MILVUS_URI": "http://your-milvus:19530",
        "OLLAMA_EMBEDDING_URL": "http://your-ollama:11434/api/embed"
      }
    }
  }
}
```

## 数据导入

```bash
python import_house_to_milvus.py <房屋列表.xls 路径>
```

支持断点续传，100万-500万条数据约需 10-35 小时（取决于 Ollama 性能）。

## 依赖

- Python >= 3.11
- Milvus >= 3.0（需要 BM25 全文检索支持）
- Ollama + bge-m3 模型（用于生成 Embedding）