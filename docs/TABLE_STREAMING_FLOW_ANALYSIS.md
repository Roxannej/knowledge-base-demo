# 图表（Markdown 表格）流式渲染链路分析

本文基于当前仓库代码，说明当大模型输出“图表”内容时（当前主要是 Markdown 表格），后端 Python 与前端分别做了什么处理，以及本次问题的关键原因。

## 结论先看

- 当前系统的“图表”本质是 **Markdown 表格**，不是独立的图表 JSON 协议。
- 后端通过 SSE 返回 `data: {"type":"token","content":"..."}` 事件，前端逐段拼接 `content` 再做 Markdown 渲染。
- 表格显示异常通常不是 SSE 协议本身问题，而是“内容在链路中被转义/拼接后不再是标准换行表格块”导致。
- 当前前端增加了两层兜底：
  - 表格块规范化（补分隔行、统一列数）
  - 删除可见转义符（把字面量 `\\n`/`\\r\\n`/`\\t` 去掉）

---

## 1) 后端（Python）对大模型返回数据做了什么

对应文件：

- `backend/agent/streaming.py`
- `backend/agent/output_processor.py`

### 1.1 生成与流式拆分

在 `stream_rag_sse_events()` 中，后端会：

1. 调用 `llm.astream(...)` 获取增量输出；
2. 用 `_extract_text_delta()` 抽取每个 chunk 的文本；
3. 交给 `StreamMarkdownProcessor.push(delta)` 处理；
4. 每个可下发片段封装为 SSE：
   - `{"type":"token","content":"..."}`
   - 最后补 `metadata` 和 `done`。

### 1.2 StreamMarkdownProcessor 的作用

`output_processor.py` 的核心目标是提高 Markdown 表格稳定性：

- 支持三种模式 `raw | line | block`（由 `TABLE_STREAM_MODE` 控制）；
- `line`：按完整行输出；
- `block`：缓存整段表格后再输出，且可做规范化。

当前代码里 `resolve_stream_mode()` 默认值是 `"line"`，但 `.env` 已可显式设为：

- `TABLE_STREAM_MODE=block`

### 1.3 表格规范化逻辑（block 模式）

在 `_normalize_table_lines()` 中，后端会：

- 若缺少分隔行（`| --- |`）则自动补；
- 按表头列数统一每行列数：
  - 不足补空列；
  - 过多截断；
- 最终输出成标准多行 Markdown 表格文本。

这一步是为了降低 LLM token 随机切分导致的“半行/断行”问题。

---

## 2) 前端对图表（表格）数据做了什么

对应文件：

- `frontend/src/lib/sse.ts`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/components/MessageBubble.tsx`

### 2.1 SSE 解析

`parseSseDataLines(buffer)` 负责：

- 以 `\n\n` 切分 SSE frame；
- 识别 `data:` 行并取 payload；
- `JSON.parse(payload)` 得到事件对象；
- 返回 `events + rest`（支持半包拼接）。

### 2.2 消息拼接

`HomePage.tsx` 中：

- `token` 事件：把 `ev.content` 追加到 assistant 消息；
- `metadata` 事件：写入 `confidence`/`sources`；
- `done` 事件：结束 streaming 状态。

因此 UI 里最终用于渲染的是多个 token 拼接后的完整字符串。

### 2.3 Markdown 表格渲染与兜底

`MessageBubble.tsx` 对 assistant 内容做了两步预处理后再交给 `ReactMarkdown + remark-gfm`：

1. `removeVisibleEscapes(text)`：删除字面量 `\\n`、`\\r\\n`、`\\t`；
2. `normalizeMarkdownTables(md)`：识别表格块并规范化（补分隔行、统一列数）。

最后由 `ReactMarkdown` 渲染；表格样式由 Tailwind class 控制（`[&_table]`、`[&_thead_th]`、`[&_tbody_td]` 等）。

---

## 3) 本次问题根因（结合现象）

你反馈的关键现象是：

- Markdown 其他部分正常；
- 表格部分显示成 `| ... | | ... |` 的纯文本；
- 内容中出现可见 `\n`。

从链路看，根因是“表格文本在某个阶段不是标准换行结构”，常见包括：

- 字面量转义符被当普通字符保留；
- 流式片段拼接后表头/分隔行结构被破坏；
- 表格块中混入异常分隔导致 GFM 未识别为 table AST。

当前代码已通过前后端双侧兜底降低该问题概率。

---

## 4) 当前实现的边界与建议

### 边界

- 系统目前处理的是 Markdown 表格，不是 ECharts/Plotly 这类结构化图表对象；
- `removeVisibleEscapes()` 当前是“删除转义符”，会牺牲部分换行信息；
- 若未来出现复杂代码块/混合文本，过于激进的删除策略可能影响排版。

### 建议

- 若业务允许，优先保证上游输出为“真实换行”而不是字面量 `\\n`；
- 后端优先使用 `TABLE_STREAM_MODE=block`；
- 若后续要支持真正图表，建议引入独立事件类型（如 `type:"chart"` + schema）而不是复用 Markdown 文本。

---

## 5) 一句话总结

当前“图表展示”链路本质是：**LLM Markdown 文本 -> 后端 SSE token 化 -> 前端拼接与表格规范化 -> ReactMarkdown/remark-gfm 渲染**；问题核心在于“文本结构是否保持为可被 GFM 识别的表格块”。

