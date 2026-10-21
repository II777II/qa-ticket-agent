# 运行与部署

## 三种跑法

### 1. 开发：前后端分离（推荐日常改代码）

```powershell
# 终端 A：后端
conda activate qa-ticket
cd E:\Code\chatgpt\qa-ticket-agent
python -m uvicorn backend.api.app:app --reload --port 5179

# 终端 B：前端
cd E:\Code\chatgpt\qa-ticket-agent\frontend
npm run dev        # http://127.0.0.1:5173，/chat 与 /api 由 Vite 代理到 5179
```

浏览器只跟 5173 说话（同源），所以 SSE 不受 CORS 约束；后端 `CORS_ORIGINS` 只作绕过代理直连时的兜底。

### 2. 演示：后端同源托管（一个地址，最稳）

```powershell
npm --prefix frontend run build          # 产出 frontend/dist
python -m uvicorn backend.api.app:app --port 5179
# 浏览器打开 http://127.0.0.1:5179/     ← 首页就是前端，/docs 仍是接口文档
```

后端启动时检测到 `frontend/dist` 就托管它（`/` 返回首页、`/assets/*` 返回静态资源）。
产物不存在时 `/` 会返回一段 JSON 说明，方便判断是不是忘了构建。
换目录用 `FRONTEND_DIST` 环境变量指定。

### 3. 单机容器：Docker Compose（单后端容器）

```powershell
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
```

镜像采用两个阶段：

1. `node:22-alpine` 构建 `frontend/dist`。
2. `python:3.11-slim` 安装后端依赖，并复制 `backend/` 与前端产物。

FastAPI 继续同源托管 `/` 和 `/assets/*`，容器只暴露 `5179`：

```text
http://127.0.0.1:5179/
http://127.0.0.1:5179/docs
```

Compose 使用可选的上层 `.env`，文件不存在时仍以 Mock/JSON 默认值启动，并配置容器健康检查。
构建上下文由根目录 `.dockerignore` 排除 `.env`、Node 依赖、测试、脚本和缓存。

### 4. PGVector 知识检索

先确认目标库已安装 `vector` 扩展，并配置：

```env
RETRIEVER=pgvector
DATABASE_URL=postgresql+psycopg://qa_ticket:change-me@127.0.0.1:5432/qa_ticket
PGVECTOR_COLLECTION=kb_chunk
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_API_KEY=sk-xxxx
```

首次或重建索引：

```powershell
python -m backend.scripts.ingest_pgvector --reset
```

只做离线管线验证时可设置 `EMBEDDING_PROVIDER=mock`，无需网络和 Key，但假向量不能代表真实
语义检索效果。PGVector 使用 LangChain 标准集合表 `langchain_pg_collection` 和
`langchain_pg_embedding`，不迁移现有 7 张知识库业务表。

## 生产化升级的具体步骤

代码不需要改，只改配置 + 装依赖 + 打开对应服务：

| 目标 | 装什么 | 改 .env | 代码位置 |
| --- | --- | --- | --- |
| 长期记忆 / 多实例共享 | `langgraph-checkpoint-postgres` | `CHECKPOINTER=postgres`、`DATABASE_URL=...` | `infrastructure/llm.py` 的 `create_checkpointer()` 已留分支 |
| 工单入库 | `sqlalchemy`、`psycopg[binary]` | `TICKET_STORE=postgres` | 在 `infrastructure/storage.py` 增加 Postgres 仓储类 |
| 订单入库 | `sqlalchemy`、`psycopg[binary]` | `ORDER_STORE=postgres` | 按 `docs/sql/postgres_schema.sql` 建表，在 `infrastructure/storage.py` 增加 Postgres 仓储 |
| 向量检索 | `langchain-postgres` + 嵌入模型 | `RETRIEVER=pgvector`、`DATABASE_URL`/`EMBEDDING_*` | `infrastructure/vector_store.py` |
| 多模型网关 | `langchain-litellm` | `LLM_PROVIDER=litellm` | `infrastructure/llm.py` 的 `create_llm()` 加分支 |
| 会话缓存 / 限流 | `redis` | `REDIS_URL=...` | 新增 |
| LLM 可观测性 | `langfuse>=5` | `LANGFUSE_ENABLED=true` 等 | `infrastructure/observability.py` 的 Langfuse 适配 |

每个分支现在都会抛一个说明性错误（告诉你缺哪个包、要开哪个服务），不会静默降级。

## Langfuse Cloud / 自托管

在 `.env` 配置：

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

- 云端美国区可改为 `https://us.cloud.langfuse.com`。
- 自托管时填写实际 `LANGFUSE_BASE_URL`。
- 启用后自动追踪 LangGraph 节点、LLM 与 Retriever；`thread_id` 映射为 session。
- Langfuse 未启用、缺少 Key 或初始化异常时会自动降级，不影响 SSE 对话。
- 服务关闭时调用 Langfuse `shutdown()` 刷新后台队列。
- trace 可能包含用户输入与模型输出，接入生产前应按数据合规要求配置脱敏与访问控制。

## 电商演示数据

订单与知识库数据由生成器产出（固定种子，可重复）：

```powershell
python -m backend.scripts.generate_ecommerce_demo
```

- 50 条订单（8 种状态）+ 明细/地址/支付/退款/状态日志/库存；
- 50 篇 HTML 知识页（8 个分类）+ 文章索引 + 可直接浏览的目录页；
- 文件位置与导入步骤见 [ecommerce-demo-data.md](ecommerce-demo-data.md)；
- Postgres 目标结构见 [sql/postgres_schema.sql](sql/postgres_schema.sql)（订单 8 表 + 知识库 7 表）。

## 日志与排查

- 日志走标准输出，用 `logging.basicConfig` 的格式：`时间 级别 logger - 消息`。
- 关键日志点：知识库加载（文档数/片段数）、工单读写（新建/重复拦截）、运行时装配（各扩展点实现）、单轮失败（error 事件同时写日志）。
- 后端被重定向到文件时中文可能乱码（Windows 默认 GBK）：用 `PYTHONIOENCODING=utf-8` 启动，或直接看控制台输出。
- 常见问题：

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `/` 返回 JSON 而不是页面 | 还没构建前端 | `npm --prefix frontend run build` 后重启后端 |
| 5173 打不开 | Vite 未启动（或首次预打包较慢） | `npm run dev`，等 `ready` 后再打开 |
| `localhost:端口` 连不上 | 服务只绑了 IPv4，而 localhost 先解析到 `::1` | 用 `127.0.0.1` 访问 |
| 回答里没有引用 | 知识库为空或没有关键词命中 | 看启动日志的知识库统计，调整 `RAG_TOP_K` / 文档措辞 |
| 前端提示「连不上后端」 | 后端未启动或端口不对 | 起后端；同源托管模式下确认访问的是后端端口 |
