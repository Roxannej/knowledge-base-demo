# Day 1：向量存储持久化

## 学习主题

把当前进程内的 **`InMemoryVectorStore`** 升级为**可落盘、可重启复用**的向量索引（学习计划建议优先 **FAISS**：本地开发依赖轻、上手快）。

## 与本项目的关系（你要改什么）

| 区域 | 建议改动 |
|------|----------|
| `backend/kb_rag/` | 新增持久化实现（如 `faiss_store.py`），对外尽量保持与现有 `vector_store.py` 相同的检索/写入语义，减少上层调用方改动。 |
| `backend/app/deps.py` | 将依赖注入从「纯内存单例」改为「启动时加载磁盘索引 / 懒加载」；明确索引根目录（见下）。 |
| `backend/app/main.py`（或负责上传的路由模块） | 上传解析、分块、embedding 完成后，**写入磁盘并保存元数据**，而不仅留在内存。 |
| 数据目录 | 约定索引目录，例如 `backend/data/indexes/`（可 `.gitignore` 忽略大文件），启动时若目录存在则加载。 |
| `README.md`（验收时补） | 增加「持久化索引」说明：目录位置、首次上传与重启后行为。 |

## Python 侧（与今日绑定）

- 用 **`pathlib.Path`** 管理索引路径，避免字符串硬拼。
- 分清 **同步 / 异步**：若向量库 API 只有同步接口，在 FastAPI 里用 **`asyncio.to_thread`**（或等价方式）避免阻塞事件循环，并理解「为何会卡」。

## 实操任务（按顺序）

1. 在 `backend/kb_rag` 增加持久化向量存储模块（如 FAISS 封装）。
2. 保留现有检索接口风格，能继续被 `retrieval.py`、agent 的 `search_docs` 等调用。
3. 增加索引目录与初始化逻辑（不存在则创建；存在则加载）。
4. 改造上传流程：上传成功即落盘，重启服务后无需重新上传仍可检索。

## 验收标准

- 重启后端后，**仍能命中**已上传文档的问答。
- 新增文档与已有文档检索均正常。
- README 中有简短的持久化说明（可与上面「验收时补」一起做）。

## 参考文档

详细 7 日总览与后续天数衔接见同目录：`STUDY_PLAN_7_DAYS.md` 中 **Day 1** 小节。

初学者向：**Agent、RAG 与本次持久化分别对应什么** 的合并说明见 [AGENT_RAG_AND_VECTOR_PERSISTENCE_PRIMER.md](./AGENT_RAG_AND_VECTOR_PERSISTENCE_PRIMER.md)。
