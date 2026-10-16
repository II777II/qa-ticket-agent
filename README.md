# 企业IT服务台 智能问答工单 Agent POC

用一句话说清楚这件事：员工用日常语言描述问题 → Agent 先查知识库给答案并标出处 →
知识库解决不了或用户明确要求时，自动整理字段建工单 → 之后能查进度、补信息、转人工。

> 状态：阶段一、二、三（后端链路 + 工单工具 + 前端对话页）已完成，RAG 与演示文档按排期推进。

## 技术选型

| 层级 | 选型 | POC 实现 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite + Ant Design X | 已就绪（Bubble / Sender / ThoughtChain / Welcome） |
| 后端 | Python 3.11 + FastAPI，SSE 流式 | 已就绪 |
| 编排 | LangGraph StateGraph（只实现 Agent + Tool 两分支） | 已就绪 |
| 模型 | 直连 DeepSeek / OpenAI 兼容，抽象成 `BaseChatModel` | 已就绪（含 mock 演示模式） |
| 短期记忆 | `MemorySaver`，`thread_id` 隔离 | 已就绪 |
| 工具调用 | `create_ticket` / `query_ticket` / `escalate_to_human` | 已就绪 |
| 简易 RAG | 进程内检索 + 3~5 篇文档 + 引用 | 阶段四 |
| 工单存储 | JSON 文件（`backend/data/tickets.json`） | 已就绪 |
| 部署 | 本地 uvicorn + `npm run dev`；Docker Compose 预留 | docker/ 目录已放好落点 |

四个扩展点（LLM / 工具 / 记忆 / 检索）都走工厂 + 配置，业务代码只依赖 LangChain 标准接口，
所以生产化替换只改 `.env`，不动业务代码。

## 快速开始

```powershell
conda activate qa-ticket
pip install -r requirements.txt

Copy-Item .env.example .env      # 什么都不填也能跑（演示模式）

# 命令行验收：能流式输出回答即通过
python -m backend.scripts.cli_chat --once "VPN 连不上怎么办"

# 走一遍「问答 → 建单 → 查进度 → 转人工」（演示模式下也能跑）
python -m backend.scripts.cli_chat
#   你 > VPN 连不上，报错 691 怎么处理        <- 只咨询，不该建单
#   你 > 帮我建个工单，整个部门都连不上，联系我 zhang.san@corp.com
#   你 > TK-20261016-0001 处理到哪了
#   你 > TK-20261016-0001 帮我转人工
python -m backend.scripts.cli_chat --tickets     # 看当前工单列表

# 后端：起 HTTP 服务（/docs 里有交互式接口文档）
uvicorn backend.main:app --reload --port 5179

# 前端：另开一个终端
cd frontend
npm install
npm run dev            # 打开 http://127.0.0.1:5173
```

接真实模型：`.env` 里把 `LLM_PROVIDER` 改成 `deepseek`（或 `openai`），填 `LLM_API_KEY`，
`LLM_BASE_URL` 默认就是 `https://api.deepseek.com/v1`。

前端 dev server 与后端同机：页面只访问 `127.0.0.1:5173`，`/chat` 与 `/api` 通过 Vite 代理转到
`127.0.0.1:5179`（见 [frontend/vite.config.ts](frontend/vite.config.ts)）。浏览器始终同源，
所以 SSE 不受 CORS 约束，后端的 `CORS_ORIGINS` 只作为「绕过代理直连后端」的兜底。
想直连后端时，在前端目录建 `.env.local` 写 `VITE_API_BASE=http://127.0.0.1:5179` 即可。

## 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/chat` | 流式对话（SSE）。事件类型：`start` / `token` / `tool` / `ticket` / `citation`(阶段四) / `done` / `error` |
| GET | `/health` | 健康检查，返回当前 provider 与各扩展点实现 |
| GET | `/api/agent-info` | 当前 Agent 能力（模型、工具、工单数、预留的 compose 落点） |
| GET | `/api/tickets` | 工单列表，支持 `status` / `contact` / `limit` 过滤（阶段三看板用） |
| GET | `/api/tickets/{id}` | 工单详情，含时间线 |

工单落在 `backend/data/tickets.json`（可用 `DATA_DIR` 指向别处）：建单用「临时文件 + 原子替换」
写盘，同一联系人 + 同标题 + 未关闭的重复建单会被拦下、返回已有工单。

## 目录结构

```
backend/
  config.py            集中配置，决定用哪个实现
  graph.py             LangGraph 编排（Agent + Tool，预留 P-E-V-S 扩展）
  tools.py             三个 @tool：建单 / 查进度 / 转人工
  schemas.py           SSE 事件与请求体定义
  runtime.py           装配层 + 统一流式出口
  main.py              FastAPI + SSE 接口
  factories/           工厂：llm.py / memory.py(记忆) / store.py(工单存储)
  stores/json_store.py 工单 JSON 存储
  mock_llm.py          演示模式假模型
  scripts/cli_chat.py  命令行验收
  data/tickets.json    工单落盘位置（自动生成，不进版本库）
  data/kb/             阶段四的知识库文档
frontend/
  vite.config.ts       代理到后端 + 固定 127.0.0.1（避开 localhost→::1 连不上的坑）
  src/main.tsx         React 挂载 + antd 中文 locale + Ant Design X Provider
  src/App.tsx          布局：顶部状态条 + 左侧对话 + 右侧工单面板
  src/ChatPage.tsx     对话页：Bubble.List / Sender / ThoughtChain / Welcome / Prompts
  src/TicketPanel.tsx  工单面板：列表 + 详情抽屉（含处理时间线）
  src/hooks/useChat.ts 会话状态：消息列表、流式增量、工具事件合并
  src/api/agent.ts     API 层：streamChat() 手写 SSE 解析 + 工单查询
  src/types.ts         与后端 schemas.py 对应的类型
docker/                compose 升级落点（POC 不启用）
```

## 排期

| 阶段 | 内容 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| 1 | 工程搭建 + LangGraph 最小图 | 命令行流式输出模型回答 | 已完成 |
| 2 | 工具 + 短期记忆 + 工厂 | 多轮不丢上下文，工具可被调用，工单落 JSON | 已完成 |
| 3 | 前端 Ant Design X | 页面能输入、流式显示、多轮对话 | 已完成 |
| 4 | 简易 RAG + 引用 | 基于知识库作答并显示引用 | 待办 |
| 5 | 联调 + README + 演示脚本 | 端到端可演示，含话术 | 待办 |

## 生产化升级路径（POC 只预留，不实现）

| 现在 | 换成 | 改哪里 |
| --- | --- | --- |
| `MemorySaver` | `PostgresSaver` | `.env: CHECKPOINTER=postgres` |
| 进程内检索 | pgvector / Qdrant | `.env: RETRIEVER=pgvector` |
| JSON 工单文件 | Postgres 工单表 | `.env: TICKET_STORE=postgres` |
| 直连模型 | LiteLLM 网关 | `factories/llm.py` 加一个分支 |
| `logging.basicConfig`（import 时改 root 的全局副作用） | 命名 logger + 自建 `Handler`/`Formatter` | `backend/main.py` |
| 单进程 | Docker Compose | 打开 `docker/docker-compose.yml` 注释块 |

关于日志这条，升级时要带两个保护：`if logger.handlers: return`——判断的是**要挂 handler 的那个 logger**，不是 root（`basicConfig` 恰好判 root，所以 root 一旦被 uvicorn / pytest 配过，它会静默失效）；命名 logger 自己挂了 handler 之后要设 `propagate = False`，否则 root 上的 handler 会把同一条日志再打一遍。配置要分开发/生产两套时，`dictConfig` + `disable_existing_loggers: False` 比手写更好维护。

权限（RBAC）、Redis 缓存、异步任务、监控告警属于生产化范围，POC 不落代码。
