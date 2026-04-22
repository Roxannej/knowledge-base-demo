# Day 4：LangGraph 任务级工作流 + 可观测 + 多工具

## 学习主题

从「对话循环图」升级到「任务工作流图」：把一次问答拆成 `planner -> retrieve -> generate -> evaluate` 多节点流程，并让执行过程可追踪、可续写、可调试。

## 今日目标（对应代码区域）

| 区域 | 目标改动 |
|------|----------|
| `backend/agent/`（或 `backend/workflows/`） | 新增任务工作流图（至少 4 节点）与条件路由。 |
| `backend/agent/graph.py` | 保留现有对话图能力，同时提供可切换的任务级图构建入口。 |
| `backend/agent/tools.py` | 在 `search_docs` 之外新增至少 1 个职责不同的工具（如索引统计或引用格式化）。 |
| `backend/app/main.py` | 增加 `thread_id` 透传与状态查询相关接口（或参数）。 |
| `backend/agent/streaming.py` | 视产品需求，补充工作流事件流式输出（节点进度 / tool 完成事件）。 |

## 实操任务（建议顺序）

1. **先把图跑起来**：实现 `planner -> retrieve -> generate -> evaluate`，`evaluate` 根据分数或规则决定 `retry` 还是 `end`。
2. **接 checkpointer**：先用 `MemorySaver`，让同一 `thread_id` 能跨轮续写状态。
3. **补多工具最小闭环**：新增一个非检索工具，并在系统提示中约束调用时机，降低误调用。
4. **打通 LangSmith**：配置 `LANGCHAIN_TRACING_V2=true`、`LANGCHAIN_API_KEY`、可选 `LANGCHAIN_PROJECT`，确保至少 1 条 run 可见。
5. **透传可观测信息**：在调用 `graph.ainvoke` 时带 `config` 的 `tags` / `metadata`（如 `route=rag_workflow`、`env=dev`）。
6. **按需流式**：若要展示执行过程，优先输出节点事件；若只要用户体验简洁，可继续仅流式最终答案。

## 最小接口建议

- `/chat` / `/chat/stream`：支持 `thread_id`（无则自动生成，有则续写）。
- `/threads/{thread_id}`（可选）：返回最近状态快照（当前节点、重试次数、最后工具调用）。
- `/chat` 新增开关参数（可选）：如 `workflow_mode=task`，便于与旧路径并行验证。

## 验收自测建议

1. 同一 `thread_id` 连续提问两次，确认第二次能读取到前次上下文状态。
2. 人为构造低质量问题（或提高评估阈值）触发 `evaluate -> retry`，确认到达上限后结束。
3. 在 LangSmith 中查看一条完整 run，确认能看到节点顺序、工具调用与 `tags/metadata`。
4. 测试新增工具被正确选择（而非总是调用 `search_docs`）。
5. 如果开了事件流，前端能稳定显示节点进度；若未开事件流，最终答案流式输出不受影响。

## 当前进度（已落地）

- [x] 至少 4 节点任务工作流可运行（`planner -> retrieve -> generate -> evaluate`）
- [x] 条件路由可触发重试并有上限（`evaluate` 后 `retry/end`）
- [x] `thread_id + checkpointer` 生效（`MemorySaver` + `/threads/{thread_id}`）
- [x] 新增 1 个非检索工具并实际接入（`get_index_stats`）
- [x] `graph.ainvoke` 已透传 `tags/metadata`（`/chat`、`/chat/stream`）
- [ ] LangSmith 面板验收（需本地配置 `LANGCHAIN_TRACING_V2` 与 `LANGCHAIN_API_KEY` 后跑一次）

## 下一步建议

1. 本地配置 LangSmith 环境变量后，调用一次 `workflow_mode=task` 的 `/chat`。
2. 在 LangSmith 里按 tag 过滤（如 `route:chat`、`workflow:task`）确认 trace 可见。
3. 已支持 `include_workflow_events=true`（`/chat/stream`）输出 `workflow_event` 事件；可在前端展示节点进度。

## 事件流式示例

请求：

```bash
curl -N -X POST "http://localhost:5173/api/chat/stream?workflow_mode=task&thread_id=demo-t1&include_workflow_events=true" \
  -H "Content-Type: application/json" \
  -d '{"message":"总结文档里的核心优化点"}'
```

你会收到混合事件：

- `type=workflow_event`：节点进度（如 `planner/retrieve/generate/evaluate`）
- `type=token`：最终回答正文流
- `type=metadata` / `type=done`：收尾信息
