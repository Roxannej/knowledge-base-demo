# Day 6：多智能体协作（轻量版 Deep Research）

## 学习主题

实现 3 角色协作最小闭环：`Researcher -> Analyst -> Writer`，并把结果落盘为可复用研究报告。

## 今日目标（对应代码区域）

| 区域 | 目标改动 |
|------|----------|
| `backend/deep_research/` | 新增轻量 deep research 服务，封装三角色协作流程。 |
| `backend/app/schemas_http.py` | 新增 deep research 请求/响应模型。 |
| `backend/app/main.py` | 新增 `POST /deep-research` 接口，支持检索参数透传并返回报告信息。 |
| `backend/data/reports/` | 生成并保存 markdown 报告与中间产物（Researcher/Analyst）。 |

## 实操任务

1. **Researcher**：从检索内容中产出事实清单与来源。
2. **Analyst**：提炼关键洞察、风险和待确认问题。
3. **Writer**：组织为结构化 Markdown 报告。
4. **落盘留痕**：将问题、中间产物与最终报告写入 `backend/data/reports/*.md`。

## 当前进度（已落地）

- [x] 新增 `backend/deep_research/service.py`，完成三角色串行协作实现。
- [x] 新增 `POST /deep-research` 接口，支持 `index_name` 与检索策略参数。
- [x] 新增 `DeepResearchRequest` / `DeepResearchResponse`，统一请求响应结构。
- [x] 研究报告落盘到 `backend/data/reports/`，包含 question、researcher notes、analyst notes、final report。

## 调用示例

```bash
curl -X POST "http://localhost:5173/api/deep-research?index_name=default&retrieval_strategy=hybrid&hybrid_alpha=0.6" \
  -H "Content-Type: application/json" \
  -d '{"question":"请针对上传资料给出一份关于 RAG 风险与优化方向的研究报告"}'
```

## 验收自测建议

1. 调用 `/deep-research` 后应返回 `report_id`、`report_path` 和 `report_markdown`。
2. 检查 `backend/data/reports/` 下对应 `report_id.md` 是否已生成。
3. 复查报告中 `References` 与研究问题是否一致，避免无关内容。
4. 对比不同 `retrieval_strategy`（如 `similarity` vs `hybrid`）输出差异。
