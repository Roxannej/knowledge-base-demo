# knowledge-base-demo 问答总结

这份文档总结了我们刚才围绕项目代码的高频问题：Python 语法、RAG 流程、DeepSeek 调用链、以及本地内存版和商业化方案的区别。

## 1. 常见 Python 语法点

- `from pathlib import PurePath`
  - 导入 `PurePath` 类，用于纯路径字符串处理（不访问文件系统）。
- `from .xxx import yyy` 里的 `.`
  - 相对导入，表示从当前包内导入。
- `b"%PDF"` 里的 `b`
  - bytes 字面量；用于和二进制数据比较。
- `import re`
  - 正则表达式库。
- 切片 `text[start:end]`
  - 取 `[start, end)` 区间子串，含 start 不含 end。
- 列表推导式
  - `return [u for u in units if u]` 过滤空值。
- `*` 参数分隔符
  - 后续参数为 keyword-only，调用时必须写参数名。
- `_ = batch_size, show_progress_bar`
  - 显式“占位忽略”变量，常用于消除未使用参数告警。
- `if not texts`
  - 判断列表是否为空（或其他假值）。
- `# noqa: F401`
  - 忽略“导入未使用”告警（常用于依赖探测）。
- `@property`
  - 方法可像属性一样访问（`obj.size` 而不是 `obj.size()`）。
- `self`
  - 当前实例对象本身。
- `getattr(obj, "attr", default)`
  - 动态获取属性，拿不到时返回默认值。
- `isinstance(x, T)`
  - 类型判断。
- `@dataclass(frozen=True)`
  - 不可变数据类（实例创建后字段不可改）。
- `Field(...)`（Pydantic）
  - 字段约束、默认值、说明文档等。
- `@field_validator(...)`
  - 字段校验/预处理钩子。

## 2. 你项目里的 RAG 主流程（简化）

1. 上传文件到后端。
2. 本地解析文档为纯文本（`document_loader`）。
3. 本地切分 chunk（`chunking`，不是 LangChain text splitter）。
4. 文本 chunk 编码成向量（优先 `sentence-transformers`；缺依赖则 `HashEmbedding`）。
5. 向量和文本存入 `InMemoryVectorStore`。
6. 用户提问后：
   - 可能先做 multi-query（LLM 生成多个检索改写）。
   - 对每个 query 做向量检索。
   - 合并候选并 rerank（LLM 评分重排）。
   - 最终回答由 LLM 生成（`/chat/stream` 为流式）。

## 3. token、embedding、检索之间的关系

- 业务代码没有手写 tokenizer。
- token 化主要发生在模型内部（`SentenceTransformer` / DeepSeek 内部）。
- 你这层主要做：
  - 文本预处理与切分；
  - 向量化；
  - 相似度检索；
  - 重排与答案生成编排。

## 4. `llm` 到底是什么，哪里来的

- `llm` 不是用户问题字符串，而是“模型客户端对象”。
- 实际来源链路：
  - `create_rag_chat_model()` 创建 `ChatOpenAI(...)` 客户端（OpenAI 兼容，指向 DeepSeek base URL）。
  - `app/deps.py` 里的 `get_chat_model()` 返回该对象，并 `lru_cache` 缓存。
  - `main.py` 路由通过 `Depends(get_chat_model)` 注入到参数 `llm`。
  - 下游函数把 `llm` 继续当参数传递并调用 `llm.ainvoke/astream/bind_tools`。

## 5. 为什么 `llm.bind_tools(...).ainvoke(...)` 会调用 DeepSeek

- `bind_tools` 只是给同一个模型客户端添加工具 schema，不会替换后端。
- 真正决定调用哪家 API 的是创建 `llm` 时的配置：
  - `base_url`（例如 `https://api.deepseek.com/v1`）
  - `api_key`
  - `model`（例如 `deepseek-chat`）
- 所以 `ainvoke` 依然是向 DeepSeek 发请求，只是这次请求具备 tool-calling 能力。

## 6. `/chat` vs `/chat/stream`

- `/chat`
  - 同步接口，返回结构化 JSON（`answer/confidence/sources`）。
- `/chat/stream`
  - SSE 流式接口，前端当前主要调用这个。
  - 先发 `token` 增量，再发 `metadata`，最后发 `done`。

## 7. 文档切分是否用 LangChain

- 当前项目不是用 LangChain 的 splitter。
- 切分策略是自定义实现（`backend/kb_rag/chunking.py`）。

## 8. 本地内存版 vs 商业化的核心区别

- 当前本地版：
  - `InMemoryVectorStore` 在进程内存中；
  - 后端进程重启后数据丢失；
  - 适合开发验证和教学。
- 商业化常见：
  - 持久化存储（数据库/向量库/对象存储）；
  - 可恢复、可扩容、多租户、权限与审计、监控告警。
- Redis 不一定是主角：
  - 常用于缓存、会话、限流、队列；
  - 向量检索常见也会用专门向量库或 `pgvector`。

## 9. “服务重启后数据丢失”具体指什么

包括但不限于：

- 你停止再启动后端（例如重启 `uvicorn`）。
- 开发模式 `--reload` 导致进程重启。
- 容器/服务器重启。

以上情况下，内存中的向量库会清空，需要重新上传入库。

---

如果你后续希望，我可以再补一版：

- “请求从前端到 DeepSeek 再回前端”的时序图版本；
- 或“如何从内存版平滑升级到持久化版（最小改动）”的实施清单。
