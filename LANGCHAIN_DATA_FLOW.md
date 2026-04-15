# 通用 LangChain 数据处理流程（RAG / Agent 视角）

本文档描述一个与具体项目解耦的、可复用的 LangChain 数据处理路径，适合用于设计问答系统、知识库检索和工具型 Agent。

---

## 1. Ingestion（离线建库阶段）

目标：把原始文档加工成可检索的向量索引。

1. **Load**：读取 PDF、Word、网页、数据库记录等数据源。  
2. **Normalize**：清洗乱码、统一编码、去噪（页眉页脚、重复段）。  
3. **Chunk**：按语义或长度切分文本（可设置 overlap）。  
4. **Embed**：将每个 chunk 转为向量。  
5. **Index**：写入向量库（FAISS、Milvus、PGVector、Pinecone 等），并存储 metadata。

常见 metadata：

- `doc_id` / `chunk_id`
- `source`（文件名、URL）
- `page` 或 `section`
- `created_at` / `tags`

---

## 2. Online Retrieval（在线检索阶段）

目标：把用户问题映射到最相关的上下文片段。

**Query（用户问题）**  
↓  
**Query Rewrite / Multi-Query（可选）**  
↓  
**Embedding（问题向量化）**  
↓  
**Vector Search（召回候选）**  
↓  
**Hybrid / Filter（可选：关键词检索、metadata 过滤）**  
↓  
**Rerank（可选：交叉编码器或 LLM 精排）**  
↓  
**Top-K Context（最终上下文）**

说明：

- Multi-Query 用于提升召回率。  
- Rerank 用于提升精度，减少“看起来相似但不相关”的片段。  
- Top-K 不宜过大，避免上下文膨胀和成本增加。

---

## 3. Generation（生成阶段）

目标：让 LLM 基于检索证据回答，而不是凭空发挥。

1. **Prompt Assemble**：系统提示词 + 用户问题 + Top-K Context。  
2. **LLM Invoke**：调用模型生成回答（同步或流式）。  
3. **Post-process**：格式化答案、提取引用来源、置信度估计（可选）。  
4. **Guardrails**：做输出校验（JSON schema、敏感信息过滤、长度限制）。

常见输出结构：

- `answer`
- `sources`
- `confidence`
- `follow_up_questions`（可选）

---

## 4. Agent Loop（工具调用型流程，可选）

当系统是 Agent（不是单次 RAG）时，会出现循环：

**User Query**  
↓  
**LLM Planning（是否需要工具）**  
↓  
**Tool Call（search_docs / sql / api 等）**  
↓  
**Tool Result 回写对话状态**  
↓  
**LLM 再推理（可继续调用工具）**  
↓  
**Final Answer（无更多 tool_calls 时结束）**

核心点：工具结果通常不会直接返回给用户，而是先作为“证据”回灌给模型，再由模型统一生成最终回答。

---

## 5. 通用工程建议

- **召回优先，精排兜底**：先保证能“找到”，再保证“排得准”。  
- **离线可重建**：文档处理链路要可重复执行（幂等）。  
- **可观测性**：记录 query、召回片段、rerank 顺序、最终 prompt。  
- **失败可降级**：检索失败时给出解释与下一步建议，不要静默失败。  
- **成本控制**：限制 top_k、上下文 token、工具循环次数。

---

## 6. 一句话总览

LangChain 通用数据流可以概括为：  
**文档预处理建库（Ingestion） -> 在线召回与精排（Retrieval） -> 基于证据生成（Generation） -> 可选工具循环（Agent Loop）**。
