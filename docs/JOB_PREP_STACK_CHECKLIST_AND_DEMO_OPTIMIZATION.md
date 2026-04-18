# 求职向：Python + AI（RAG）技术栈必做清单 & 本仓库优化建议

面向「准备找工作」：下面每一项都写成**可自检的交付物**（你能讲清楚、能演示、能写在简历上），并标明与 **knowledge-base-demo** 的结合方式。

---

## 一、技术栈必做清单（按面试可考察程度排序）

### 1. PostgreSQL + pgvector

**学到什么程度**

- SQL：建表、索引、迁移思路、连接池；能解释 ACID 与「为什么生产用库而不是内存结构」。
- pgvector：向量列、`LIMIT` Top-K、一种索引（如 `hnsw` 或 `ivfflat`）的名字与**粗粒度**取舍；metadata 过滤（`WHERE` + 向量排序）的常见写法。

**必做交付物（简历可写）**

- [ ] 本地或 Docker 起 Postgres，启用 pgvector 扩展，建「文档块」表（id、content、embedding、doc_id、created_at 等）。
- [ ] 一条「写入 embedding + 查询 Top-K」的完整路径（可用小脚本或 API）。
- [ ] 能口述：维度、索引参数、数据量变化时延迟/召回怎么变。

**与本项目结合**

- 当前：`InMemoryVectorStore`（`backend/kb_rag/vector_store.py`）+ 进程单例（`backend/app/deps.py`），重启丢数据。
- 目标：抽象「向量存储接口」，增加 **pgvector 实现**（或并行保留内存版做测试），上传入库写库、检索读库。

---

### 2. RAG pipeline（端到端）

**学到什么程度**

- 能画**自己项目**的 pipeline：解析 → 切分 → embedding → 入库 → 检索（含 query 变换/重排）→ 拼 context → LLM →（可选）结构化/引用。
- 能指出瓶颈与失败模式：解析烂、chunk 太大/太小、检索空、context 爆窗、模型乱编。

**必做交付物**

- [ ] 一张流程图（纸笔或白板级即可），与代码目录一一对应。
- [ ] 至少改通过一个环节并能量化（例如：chunk 策略 A/B、rerank on/off 对比）。
- [ ] 能说清「同步接口 vs 流式接口」分别如何保证一致性（metadata、sources）。

**与本项目结合**

- 已有：`document_loader` / `chunking` / `embeddings` / `retrieval`（multi-query + rerank）/ `agent`（LangGraph + `search_docs`）/ `structured` / `streaming`。
- 补强：在 README 或口头面试里用「请求从进入到响应」串一遍；补**可观测**（日志字段或 LangSmith）证明你理解全链路。

---

### 3. embedding 是什么（工程向）

**学到什么程度**

- 语义向量、维度固定、同任务内模型不可混用；调用成本、批大小、缓存价值。

**必做交付物**

- [ ] 说清本项目 `create_default_embedder`（`sentence-transformers` vs `HashEmbedding`）差异及**为何 Hash 不能写进简历当生产方案**。
- [ ] 实现或设计「embedding 缓存」（内存 dict / Redis / 表上唯一约束）中的一种，避免重复编码相同 chunk。

**与本项目结合**

- 重点文件：`backend/kb_rag/embeddings.py`、`vector_store.py`。
- 面试话术：「维度 d、L2 归一化、score 用点积表示 cosine」与 `vector_store` 注释一致即可。

---

### 4. 向量检索

**学到什么程度**

- Top-K、相似度度量（cosine / L2 / inner product）与**归一化**的关系；暴力检索 vs 近似索引；简单 hybrid（关键词 + 向量）的概念。

**必做交付物**

- [ ] 能解释当前仓库「矩阵 + `argpartition`」在数据量大时的局限，以及 pgvector / FAISS / HNSW 解决什么问题。
- [ ] （可选加分）最小 hybrid：先用关键词缩小候选集再向量排序，或反之。

**与本项目结合**

- `vector_store.py` 的 `_top_k_indices`、检索入口 `retrieval.py`；面试可讲「为何先做 multi-query 再合并候选再 rerank」。

---

### 5. token / context window

**学到什么程度**

- token 是计费与长度单位；context window 上限；检索片段 + 历史 + 指令的总和需控制；截断/摘要/多轮策略能举两例。

**必做交付物**

- [ ] 在代码或配置里为「塞进模型的检索文本」设**上限**（字符或 token 估算），并能在面试说清依据。
- [ ] 说明流式路径（`streaming.py`）里二次调用模型时，输入大致由哪些部分组成、如何避免爆窗。

**与本项目结合**

- `agent/streaming.py`（transcript + 流式生成）、`tools.py` / `retrieval.py` 返回长度；可加重试或裁剪策略作为小优化项写进简历。

---

### 6. hallucination（幻觉）与 grounding

**学到什么程度**

- 无据编造、过度推断；缓解手段：强约束 prompt、检索为空时拒答、引用片段、citation 校验、低 confidence、结构化字段。

**必做交付物**

- [ ] 走读 `agent/structured.py` 与 schema，能讲 `confidence` / `sources` 的业务含义及局限。
- [ ] 至少加一条**产品规则**（例如：无检索命中时固定话术、或禁止编造 chunk_id），并能演示。

**与本项目结合**

- `schemas/rag_answer.py`、`agent/graph.py` 系统提示；面试强调「不靠只调 temperature，而是检索 + 约束 + 结构化」。

---

### 7. Redis

**学到什么程度**

- 常用场景：缓存、限流、分布式锁、简单队列；基本数据类型与 TTL；连接失败时的行为。

**必做交付物**

- [ ] 起一个 Redis，完成**一类**与 AI 相关的真实用途即可（任选）：embedding 缓存、session id → 最近问答、限流 key、异步任务队列之一。
- [ ] 能对比「只用进程内存」与「Redis」在多实例部署时的差别。

**与本项目结合**

- 当前无 Redis；与 `deps.py` 单例向量库、多 worker 部署矛盾点可主动讲「后续用外置 store + Redis 缓存 embedding」。

---

## 二、结合本仓库的优化建议（按求职性价比排序）

### P0（强烈建议做，和岗位描述重合度高）

1. **持久化向量存储（Postgres + pgvector 或至少 SQLite + 文件侧向量）**  
   - 解决：重启丢数据、无法演示「多知识库」、与生产差距过大。  
   - 落点：抽象 `VectorStore` 协议；实现 pgvector 版；迁移路径写进 README 一两段。

2. **可观测与可复盘**  
   - LangSmith 或等价 trace；请求级 `request_id`、关键阶段耗时日志。  
   - 落点：`pipeline.py` / `graph.ainvoke` / `synthesize_structured_rag_answer` 打同一 trace。

3. **上下文与成本控制**  
   - 检索拼接上限、rerank 候选上限、多 query 条数与文档对齐说明。  
   - 落点：`retrieval.py`、`tools.py` 返回格式；面试能报数字。

### P1（加分，体现「懂系统」）

4. **Redis 做 embedding 或检索结果缓存**  
   - 命中 key：`hash(text)` 或 `chunk_id`；TTL 策略能说清。

5. **混合检索或 metadata 过滤**  
   - 按 `doc_id`、上传时间过滤；与 pgvector `WHERE` 结合。

6. **基础测试与 CI**  
   - `pytest` 覆盖：chunk、vector_store top-k、一个 API 集成测试（可用 TestClient）。

### P2（时间充裕再做）

7. **多实例与安全**  
   - API Key 只走环境变量、上传文件类型与大小限制、简单 rate limit（Redis 或中间件）。

8. **评测集**  
   - 固定 20～50 问，记录「是否调用检索、sources 是否为空」；换模型可回归。

---

## 三、简历表述示例（避免空话）

- 「基于 FastAPI + LangGraph 实现 RAG：multi-query 扩展、LLM rerank、工具调用与结构化输出；将内存向量库迁移为 **PostgreSQL + pgvector**，支持持久化与 metadata 过滤。」
- 「补齐 **token/context 预算** 与检索截断策略；接入 **LangSmith** 做全链路 trace；使用 **Redis** 缓存 embedding，降低重复计算延迟。」

按你实际完成的项勾选改写，不要写未实现的功能。

---

## 四、自检：面试前 30 分钟过一遍

- [ ] 从用户上传到返回答案，说清 5～8 个步骤及对应模块名。  
- [ ] 画得出 embedding 与向量检索的输入输出形状（batch × dim）。  
- [ ] 说得出「幻觉」在本项目里可能从哪几个环节进来、你怎么缓解。  
- [ ] 说得出为什么 job 要求 Postgres/Redis 时，你现在的 demo 还缺哪一块、你计划怎么补。

---

（本文件为求职向清单与路线建议，与 `STUDY_PLAN_7_DAYS.md` 可并行使用：前者偏「岗位匹配度」，后者偏「按天迭代」。）
