# knowledge-base-demo

一个基于 FastAPI + LangGraph 的 RAG 演示项目：  
上传文档（Word / PDF / TXT）后进行向量检索，再由 LLM 生成答案（支持 SSE 流式返回）。

## 功能特性

- 文档上传与解析：`/upload`（multipart）与 `/upload/binary`（raw bytes）
- 自定义文本切分（段落 + 句子 + 超长兜底切分）
- 向量检索（进程内向量库 `InMemoryVectorStore`）
- Multi-query 召回 + LLM rerank
- Agent 工具调用（`search_docs`）
- 两种对话接口：
  - `/chat`：同步结构化 JSON
  - `/chat/stream`：SSE 流式 token + metadata
- 前端页面（Vite + React）实时展示流式回答

## 技术栈

- Backend: Python 3.11+, FastAPI, LangGraph, LangChain
- Frontend: React + Vite + TypeScript
- LLM 接入: OpenAI 兼容接口（默认配置 DeepSeek）
- Embedding:
  - 优先 `sentence-transformers`（需安装 torch）
  - 缺依赖时自动降级到 `HashEmbedding`（仅兜底，不建议生产）

## 目录结构

```text
backend/
  app/
    main.py           # FastAPI 路由入口
    deps.py           # 依赖注入：llm / vector store
  agent/
    graph.py          # LangGraph agent + tools 循环
    tools.py          # search_docs 工具
    pipeline.py       # /chat 编排
    streaming.py      # /chat/stream 编排
  kb_rag/
    document_loader.py
    chunking.py
    embeddings.py
    vector_store.py
    multi_query.py
    rerank.py
    retrieval.py
    llm.py            # ChatOpenAI(兼容网关)创建
frontend/
  src/pages/HomePage.tsx  # 前端调用 /chat/stream
Makefile
```

## 快速开始

### 1) 安装依赖

在项目根目录执行：

```bash
make install
```

> 需要本机有 Python 3.11+ 与 Node 18+。

### 2) 配置后端环境变量

复制示例文件：

```bash
cp backend/.env.example backend/.env
```

最小必填（默认 DeepSeek）：

- `OPENAI_BASE_URL=https://api.deepseek.com/v1`
- `OPENAI_API_KEY=...`
- `DEEPSEEK_API_KEY=...`（建议与上面一致）
- `OPENAI_MODEL=deepseek-chat`

### 3) 启动后端

```bash
make dev-backend
```

默认监听：`http://localhost:8000`

### 4) 启动前端

新开一个终端：

```bash
make dev-frontend
```

默认地址：`http://localhost:5173`

## 使用流程

1. 打开前端页面
2. 上传文档（建议先 `replace=true` 清空旧库）
3. 在聊天框提问
4. 前端通过 `/chat/stream` 接收 SSE 事件，实时渲染答案

## API 概览

### `GET /health`

健康检查，返回：

- 服务状态
- 支持的上传扩展名
- 当前 embedding 后端
- OpenAI/DeepSeek 环境变量是否配置

### `POST /upload`

`multipart/form-data` 上传文件，字段：

- `file`（必填，兼容 `upload`）
- `description`（可选，会并入文本前缀）
- query: `replace`（是否先清空向量库）

### `POST /upload/binary`

原始二进制请求体上传，query:

- `filename`（必填，含扩展名）
- `replace`（可选）
- `description`（可选）

### `POST /chat`

同步对话，输入：

```json
{ "message": "..." }
```

返回结构化 JSON（`answer` / `confidence` / `sources`）。

### `POST /chat/stream`

SSE 流式对话，输入同 `/chat`，返回事件：

- `type=token`：增量文本
- `type=metadata`：`confidence` 与 `sources`
- `type=done`：结束
- `type=error`：错误信息

## RAG 处理流程（简版）

1. 文档解析为纯文本
2. 自定义规则切分为 chunks
3. chunks 编码为向量并写入内存向量库
4. 提问时生成 multi-query（LLM）
5. 各 query 在向量库检索并合并候选
6. LLM rerank 候选
7. 生成最终回答（同步或流式）
8. 输出结构化元数据（confidence / sources）

## 关于数据持久化

当前向量库为 `InMemoryVectorStore`：

- 数据仅保存在后端进程内存中
- 服务重启（包括 `--reload` 重启）后数据会丢失

如果要用于生产，建议替换为持久化向量存储（如 pgvector / Milvus / Qdrant / Pinecone 等）。

## 常见问题

- **401 / invalid_api_key**
  - 检查 `backend/.env` 的 key 是否为 DeepSeek 平台签发
  - 确认 `OPENAI_BASE_URL` 与 `OPENAI_MODEL` 匹配当前网关
- **上传后提示未提取到文本**
  - 可能是扫描件或图片 PDF；可在上传时添加 `description`
- **重启后问答失效**
  - 属于内存向量库预期行为，需重新上传

## 开发命令（Makefile）

- `make install`：安装全部依赖
- `make install-backend`
- `make install-frontend`
- `make dev-backend`
- `make dev-frontend`
- `make upload-api FILE=/绝对路径/xxx.pdf`
- `make upload-binary-api FILE=/绝对路径/xxx.pdf`

