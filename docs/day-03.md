# Day 3：检索策略升级（MMR + 阈值 + 组合）

## 学习主题

在 Day 2 多索引管理基础上，给检索链路增加可切换策略层：`similarity`、`mmr`、`score_threshold`、`hybrid`。

## 本次实现（对应代码）

| 区域 | 改动 |
|------|------|
| `backend/kb_rag/retrieval.py` | 新增 `RetrievalConfig` 与策略工厂逻辑，支持四种检索策略并保留 multi-query + rerank 主流程。 |
| `frontend/src/pages/HomePage.tsx` | 新增检索策略控制面板，可直接在页面切换策略并调整 `score_threshold` / `mmr_lambda` / `hybrid_alpha`。 |
| `backend/agent/tools.py` | `search_docs` 支持注入策略配置，并输出调试信息（策略名、候选数、阈值过滤数、rerank 前后数量）。 |
| `backend/agent/graph.py` | 图构建函数新增 `retrieval_config` 参数，向工具透传。 |
| `backend/agent/pipeline.py` | `/chat` 主路径支持透传检索策略。 |
| `backend/agent/streaming.py` | `/chat/stream` 主路径支持透传检索策略。 |
| `backend/app/main.py` | `/chat` 与 `/chat/stream` 新增查询参数：`retrieval_strategy`、`score_threshold`、`mmr_lambda`。 |

## 使用方式

以 `/chat`（或 `/chat/stream`）为例：

- `retrieval_strategy=similarity`：传统相似度优先召回。
- `retrieval_strategy=mmr`：提高结果多样性（减少重复片段）。
- `retrieval_strategy=score_threshold&score_threshold=0.35`：过滤低分噪声片段。
- `retrieval_strategy=hybrid`：融合 similarity 与 mmr 的候选结果。
- `hybrid_alpha=0.6`：`hybrid` 下 similarity 权重（越高越偏向 similarity 排序）。

示例：

```bash
curl -X POST "http://localhost:5173/api/chat?index_name=default&retrieval_strategy=hybrid&mmr_lambda=0.6&hybrid_alpha=0.7" \
  -H "Content-Type: application/json" \
  -d '{"message":"总结文档里关于流式表格处理的关键优化点"}'
```

## 验收自测建议

1. 同一问题分别使用 `similarity` 与 `mmr`，观察 `search_docs` 返回的片段重复度是否下降。
2. 使用 `score_threshold=0.4` 对比 `0.2`，确认低相关片段明显减少。
3. 用 `hybrid` 测试长问题，确认命中覆盖度与多样性折中。
4. 检查工具输出中的 `[debug]` 行，确认策略参数生效（尤其 `threshold_filtered` 与 `rerank` 变化）。
