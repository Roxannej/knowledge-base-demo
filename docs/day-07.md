# Day 7：工程化收尾（测试、部署、文档）+ LangSmith 评测入门

## 学习主题

把前 6 天能力串成“可交付项目”，补齐最小测试、最小部署、最小文档和最小评测闭环。

## 今日目标（对应代码区域）

| 区域 | 目标改动 |
|------|----------|
| `backend/tests/` | 增加核心接口最小自动化测试（优先健康检查与基础聊天路径）。 |
| `backend/requirements.txt` | 确认测试依赖与运行依赖完整，避免新机器缺包。 |
| `backend/Dockerfile` | 提供后端容器化入口，支持一键构建运行。 |
| `frontend/Dockerfile` | 提供前端容器化入口（开发或生产模式二选一先落地）。 |
| `docker-compose.yml` | 编排前后端联合启动，统一环境变量注入。 |
| `README.md` | 更新工程化说明：启动方式、测试方式、LangSmith 配置与注意事项。 |

## 实操任务

1. **最小测试闭环**：新增 `pytest` 用例，覆盖至少 1~2 条核心接口。
2. **最小部署闭环**：新增前后端 Dockerfile 与 `docker-compose.yml`。
3. **最小文档闭环**：补齐 README 的运行、测试、排障、环境变量说明。
4. **最小评测闭环（建议）**：记录 LangSmith Dataset / Evaluation 的入口命令与指标。

## 当前进度（待完成）

- [x] 新增 `backend/tests/` 并接入 `pytest`
- [x] 至少 1~2 条核心接口自动化测试可运行（`health` + `indexes` 生命周期）
- [x] 新增 `backend/Dockerfile`
- [x] 新增 `frontend/Dockerfile`
- [x] 新增根目录 `docker-compose.yml`
- [x] README 新增 Day 7 工程化说明
- [ ] （建议）补充 LangSmith 轻量评测入口

## 验收自测建议

1. 本地执行测试命令通过（如 `pytest`）。
2. `docker compose up --build` 能同时启动前后端。
3. 新机器按 README 文档可在 30 分钟内跑起核心功能。
4. LangSmith（若配置）可看到至少一条带 tags/metadata 的可追踪运行记录。

## 建议执行顺序（现在就能开干）

1. 先做测试：创建 `backend/tests/test_health_and_chat.py`，把最小回归用例稳定下来。
2. 再做容器：补齐 Dockerfile 与 compose，保证演示环境可复现。
3. 最后补文档：把“怎么跑、怎么测、怎么排障”沉淀到 README。
