# Day 2：索引生命周期管理（IndexManager）

## 学习主题

在 Day 1 持久化向量库基础上，补齐多索引管理能力：创建、列表、详情、删除，以及上传时选择目标索引。

## 本次实现（对应代码）

| 区域 | 改动 |
|------|------|
| `backend/kb_rag/index_manager.py` | 新增 `IndexManager`，统一管理索引目录、注册表、实例缓存与元数据。 |
| `backend/app/main.py` | 新增索引管理 API：`POST /indexes`、`GET /indexes`、`GET /indexes/{name}`、`DELETE /indexes/{name}`。 |
| `backend/app/main.py` | 上传与聊天接口支持 `index_name` 参数，按索引隔离读写。 |
| `backend/app/schemas_http.py` | 新增 `CreateIndexRequest` 与 `IndexResponse`，统一请求/响应结构。 |
| `backend/app/deps.py` | 注入 `IndexManager`，由依赖层管理索引根目录与共享实例。 |

## 验收自测建议

1. `POST /indexes` 创建新索引（如 `finance`）。
2. `GET /indexes` 能看到 `default` 与新索引。
3. 上传时传 `index_name=finance`，确认仅该索引文档数增长。
4. 聊天时分别指定不同 `index_name`，验证回答来源隔离。
5. 对不存在索引调用上传/聊天/详情，确认返回友好错误。
