# knowledge-base-demo 学习补齐计划（7 天）

## 计划目标

**主线目标：巩固 Python 工程能力，并系统掌握 LangChain 生态（LangChain Core / LangGraph，并接上 LangSmith）。**

基于你当前的 `knowledge-base-demo`，在 7 天内补齐与 `lc-studylab` 的核心能力差距，重点从“能跑 Demo”升级到“有工程化能力的 AI 应用”：

- **Python**：异步与类型、Pydantic、测试与项目结构（与后端改动同步练）
- **LangChain / LangGraph**：Runnable 与 `config`（callbacks/metadata）、多工具编排、`checkpointer` 与 `thread_id`、图事件流（与现有 `agent` 图对照学）
- **LangSmith**：本地/云端 trace、run 的 tags 与 metadata、（可选）数据集与轻量评测
- 持久化向量索引与索引管理
- LangGraph 任务级工作流（含重试与状态）
- Guardrails 安全与结构化输出
- 多智能体协作（轻量版）
- 工程化交付（脚本、文档、部署）

---

## 学习原则

- 先做最小可用版本，再增强
- 每天都要有“可运行结果”
- 每个阶段都留验收标准，避免只写代码不验证
- 优先复用你现有目录结构，不做大规模推倒重来
- **Python 与 LangChain 交织练习**：读官方文档时，用手写最小脚本验证（venv、`asyncio`、打印 `Runnable` 的 invoke 结果），再回到本仓库集成

---

## 与当前 demo 对照：需补充的学习地图

你仓库里已具备：`ChatOpenAI`、`@tool`、`bind_tools`、`StateGraph` + `ToolNode`、结构化输出与两段式流式回答。**下面是要刻意补上的缺口**（与后文「每日任务」对应）：

| 主题 | 现状（概念） | 建议补什么 |
|------|--------------|------------|
| **LangSmith** | 依赖与代码中未接 trace | 开启 tracing；给 graph / 工具 / 结构化步骤打 tags；学会在 UI 里读一条 run 的耗时与 token |
| **LangChain Runnable** | 多为直接调用函数与模型 | 把「可复现的一小段链」写成 `Runnable`，统一传入 `config={"callbacks":...}` 或 LangSmith 环境变量，体会与裸调用的差别 |
| **LangGraph 进阶** | 单循环 agent ↔ tools | `MemorySaver` / DB checkpointer、`thread_id`、条件边更复杂时自定义 state；需要时用 `stream_events` 观察节点级事件 |
| **多工具** | 当前以 `search_docs` 为主 | 同一 `tools` 列表挂多个 `@tool`，用系统提示约束「何时调用哪个」；理解 `ToolNode` 与多条 `tool_calls` 的回合合并 |
| **流式语义** | 图 `ainvoke` 后再单独 `astream` 最终回答 | 明确产品要「仅最终 token」还是「工具/节点事件」；后者需学 LangGraph 的 stream / events 模式 |

**Python 侧（贯穿 7 天、不必单独占满一天）**：`async`/`await` 与 FastAPI 路由、`typing`（`TypedDict`、泛型）、`pathlib`、`pydantic` 校验与自定义 validator、用 `pytest` 写最小异步测试。每日任务里会点名与当日最相关的点。

---

## Day 1：向量存储持久化（替换内存库）

### 学习主题

从 `InMemoryVectorStore` 升级为可持久化方案（建议先 FAISS，本地开发成本最低）。

### Python 侧（与今日任务绑定）

- 用 `pathlib.Path` 管理索引目录，避免手写字符串拼接路径
- 明确同步/异步边界：若某库只有同步 API，用 `asyncio.to_thread` 或后台任务包装（理解为何阻塞）

### 实操任务

- 在 `backend/kb_rag` 增加持久化向量存储模块（如 `faiss_store.py`）
- 保留现有检索接口风格，减少上层改动
- 增加索引目录（如 `backend/data/indexes`）与初始化逻辑
- 改造上传接口，使上传后可以落盘保存
- 服务重启后支持继续问答（无需重传）

### 验收标准

- 重启后端后，问答仍可命中文档
- 新增与已有文档检索都正常
- README 增加“持久化说明”

---

## Day 2：索引生命周期管理（IndexManager）

### 学习主题

补齐“索引创建、更新、删除、列表、元数据”完整管理能力。

### Python 侧

- 用 **Pydantic**（或 `TypedDict`）定义索引元数据模型，练习字段校验与 API 请求体/响应体一致性
- FastAPI 依赖注入：把 `IndexManager` 或 store 作为依赖，减少在路由里手写单例

### 实操任务

- 在 `backend/kb_rag` 新增 `index_manager.py`
- 设计索引元数据（名称、描述、文档数、更新时间）
- 增加 API：
  - `POST /indexes` 创建
  - `GET /indexes` 列表
  - `GET /indexes/{name}` 详情
  - `DELETE /indexes/{name}` 删除
- 上传接口支持指定 `index_name`

### 验收标准

- 能维护多个知识库索引
- API 文档可直接测试索引增删查
- 错误场景（索引不存在、重复创建）有友好报错

---

## Day 3：检索策略升级（MMR + 阈值 + 组合）

### 学习主题

在现有 multi-query + rerank 基础上，补齐“检索器策略层”。

### LangChain 侧（小步）

- 阅读 `langchain_core` 里与 **Retriever / Runnable** 相关的概念：把「选策略 → 召回」看成可组合的 `Runnable`（哪怕先只在一个小函数里用 `|` 拼接两步）
- 为后续 LangSmith 打点：给不同策略的 run 设不同 `tags`（概念上理解即可，Day 4 落地环境变量）

### 实操任务

- 增加统一 retriever 工厂（`similarity` / `mmr` / `score_threshold`）
- 支持通过请求参数切换检索策略
- 尝试实现“组合检索器”最小版本（可选）
- 输出检索调试信息（命中数、阈值过滤后数量）

### 验收标准

- 同一问题可切换不同检索策略
- MMR 结果相对普通相似度有更高多样性
- 阈值策略能明显减少低相关噪声片段

---

## Day 4：LangGraph 任务级工作流 + 可观测 + 多工具

### 学习主题

从“对话循环图”升级为“任务工作流图”（多节点状态机），并**接上 LangSmith**、理解 **checkpointer / thread_id**、练习 **多工具** 与（可选）**图级事件流**。

### LangSmith（今日必做其一：至少能看图在面板里跑起来）

- 安装并配置 `langsmith`（或按官方文档仅用环境变量开启 tracing），本地跑一条 `graph.ainvoke` 能在 LangSmith 看到完整 trace
- 学会设置：`LANGCHAIN_TRACING_V2`、`LANGCHAIN_API_KEY`、可选 `LANGCHAIN_PROJECT`
- 在 `config` 里传入 `metadata` / `tags`（例如 `{"route":"rag","env":"dev"}`），便于过滤

### LangGraph 进阶（与多节点工作流一起做）

- 使用 **checkpointer**（如 `MemorySaver` 入门，后续可换持久化实现），同一 `thread_id` 多次 `invoke` 能续写状态
- 阅读官方文档：**conditional edges**、自定义 `state`（除 `MessagesState` 外何时需要额外字段）
- **多工具**：在现有 `bind_tools` + `ToolNode` 思路上，增加至少 1 个与 `search_docs` 职责不同的工具（例如 `get_index_stats` 只读元数据、或 `format_citation` 纯文本处理）；用系统提示写清调用时机，避免模型乱选
- **流式（二选一即可）**：要么保持「图结束后再流式最终回答」，要么尝试 `stream` / `stream_events` 把节点或 tool 完成事件透出（与产品需求对齐）

### 实操任务

- 在 `backend/agent` 或 `backend/workflows` 增加学习工作流：
  - planner -> retrieve -> generate -> evaluate
- 增加条件路由：`evaluate` 后决定 `retry` 或 `end`
- 增加 **thread_id** 与状态查询接口（与 checkpointer 打通）
- 增加工作流事件流式输出（SSE）（可与上节「图级事件」二选一深度）
- **LangSmith**：保证本日主要路径在面板可追溯；至少一条 run 带自定义 tag

### 验收标准

- 至少 4 个节点可观察执行顺序
- 低分时会自动重试，达到上限后结束
- 可按 thread_id 查看当前状态（与 checkpoint 行为一致）
- LangSmith 上能看到至少一次完整图执行；多工具场景下 tool 选择在 trace 中可读

---

## Day 5：Guardrails 安全层

### 学习主题

给输入与输出加可配置的“安全与质量约束”。

### Python / LangChain 侧

- **Pydantic**：输出侧与现有 `RAGStructuredAnswer` 等模型对齐，练习 `model_validator` / 字段级 `Field` 约束
- **LangChain**：若有「模型二次审核」步骤，可用独立 `Runnable` 或小型 chain，便于同一套 LangSmith trace 里看到 guard 节点

### 实操任务

- 新建 `backend/guardrails` 模块（输入验证、输出验证）
- 输入侧：长度、敏感词、简单 prompt injection 检测
- 输出侧：结构校验（Pydantic）、来源引用完整性检查
- 在 `/chat` 和 `/chat/stream` 主路径挂载 guardrails

### 验收标准

- 恶意输入被拦截或降级处理
- 输出格式不符合 schema 时有清晰错误
- 可开关严格模式（strict / relaxed）

---

## Day 6：多智能体协作（轻量版 Deep Research）

### 学习主题

实现 3 角色协作最小闭环：Researcher / Analyst / Writer。

### LangChain / LangGraph 侧

- 体会「单图多工具」与「多子图 / 多节点角色」的分工：何时用**一个 agent 多工具**，何时拆成**多个节点或子图**（本日用子图或清晰节点边界实践一次）
- 继续用 LangSmith 看**子步骤**耗时，定位哪一角色最费 token

### 实操任务

- 新建 `backend/deep_research` 目录
- 设计子智能体职责：
  - Researcher：收集信息
  - Analyst：提炼要点
  - Writer：组织成报告
- 将协作流程挂到 LangGraph
- 结果保存到文件（如 `backend/data/reports`）

### 验收标准

- 输入研究问题后能生成结构化 Markdown 报告
- 报告有明确章节与来源
- 中间产物可追踪（日志或落盘）

---

## Day 7：工程化收尾（测试、部署、文档）+ LangSmith 评测入门

### 学习主题

把前 6 天能力串成“可交付项目”，并建立**可回归**的 LangChain 行为基线（轻量评测）。

### LangSmith（可选但强烈建议完成「最小闭环」）

- 了解 **Datasets**：录入 10～20 条固定问题（含期望行为说明，不必长答案全文）
- 跑一轮 **Evaluation**（官方示例或导出 trace 再评）：关注「是否调用检索工具」「结构化字段是否合法」等可自动判的指标
- 把「评测入口」写进文档（命令或脚本名即可），方便以后改 prompt / 换模型时对比

### Python 侧

- 用 `pytest`（含 `pytest-asyncio` 若需要）给 1～2 个核心路径写异步测试
- 整理 `requirements.txt` / 虚拟环境说明，确保 `langsmith` 等新增依赖有记录

### 实操任务

- 增加关键脚本：初始化索引、快速测试、演示脚本
- 增加最小测试集（核心 API 和关键函数）
- 增加 Dockerfile 与 `docker-compose.yml`（前后端可一键启动）
- 更新 README：架构图、接口总览、学习路径（**含 LangSmith 配置说明与隐私注意**：勿提交 API Key）

### 验收标准

- 新机器按文档可在 30 分钟内跑起来
- 关键接口有基础自动化测试
- 代码结构和文档能支持后续继续迭代
- （建议）LangSmith 上有一份可复跑的小数据集或评测记录，作为后续迭代的参照

---

## 建议目录增量（参考）

```text
backend/
  guardrails/
    input_validators.py
    output_validators.py
    middleware.py
  workflows/
    study_flow_graph.py
    state.py
  deep_research/
    deep_agent.py
    subagents.py
  kb_rag/
    faiss_store.py
    index_manager.py
    retrievers.py
docs/
  STUDY_PLAN_7_DAYS.md
# 环境变量（本地 .env，勿提交密钥）：LangSmith 见官方 LANGCHAIN_* 变量说明
```

---

## 每日打卡模板

你可以每天按下面模板记录进度：

```md
## Day X 完成情况
- [ ] 今日目标完成
- [ ] 代码可运行
- [ ] 接口已自测
- [ ] 文档已更新

### 今日产出
- 新增文件：
- 改造接口：
- 遇到问题：
- 明日计划：
```

---

## 最终里程碑（完成 7 天后）

- [ ] 支持持久化知识库，不再因重启丢数据
- [ ] 支持多索引管理和检索策略切换
- [ ] 拥有可观测的 LangGraph 任务工作流
- [ ] 具备基础 Guardrails 安全机制
- [ ] 具备轻量多智能体协作能力
- [ ] 拥有可部署、可演示、可继续扩展的项目骨架

