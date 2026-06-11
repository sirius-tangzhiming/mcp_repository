# mcp-project-search

项目搜索 MCP Server，基于 Milvus 向量数据库，支持语义搜索、混合搜索和标量精确查询。

## 功能

| 工具 | 说明 |
|---|---|
| `search_project` | 语义搜索，根据自然语言描述搜索项目 |
| `hybrid_search_project` | 混合搜索（向量语义 + BM25 关键词），对口语化短关键词效果更好 |
| `query_project_by_name` | 按项目名称精确查询 |
| `query_projects_by_filter` | 按标量字段（省份/城市/状态等）过滤查询 |

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MILVUS_URI` | `http://10.15.208.159:19530` | Milvus 连接地址 |
| `OLLAMA_EMBEDDING_URL` | `http://10.15.208.159:11434/api/embed` | Ollama Embedding API 地址 |

## 安装

```bash
# 从 GitHub 安装
pip install git+https://github.com/sirius-tangzhiming/mcp_-repository.git

# 或用 uvx 直接运行
uvx --from git+https://github.com/sirius-tangzhiming/mcp_-repository.git mcp-project-search
```

## MCP 客户端配置

```json
{
  "mcpServers": {
    "project-search": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/sirius-tangzhiming/mcp_-repository.git",
        "mcp-project-search"
      ],
      "env": {
        "MILVUS_URI": "http://your-milvus:19530",
        "OLLAMA_EMBEDDING_URL": "http://your-ollama:11434/api/embed"
      }
    }
  }
}
```

## 依赖

- Python >= 3.11
- Milvus >= 3.0（需要 BM25 全文检索支持）
- Ollama + bge-m3 模型（用于生成 Embedding）
