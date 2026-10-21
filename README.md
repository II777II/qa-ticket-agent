# 电商智能助手 POC（订单查询 + 知识库问答）

用一句话说清楚这件事：用户用日常语言描述问题 → Agent 先查电商知识库给答案并标出处 →
订单问题转到订单查询，售后问题生成待确认草稿 → 平台另提供独立的订单查询页与知识库检索页。

> 状态：五个阶段全部完成——后端链路、工单工具、前端对话页、RAG 引用、演示文档与联调。
> 文档见 [docs/](docs/architecture.md)：架构与执行路径、演示脚本与话术、追问应对、运行与部署。
> 当前分支 `langgraph-native` 使用 `StreamWriter + custom` 和 FastAPI 内置 SSE；
> `sse-abstract` 保留状态投影与手写 SSE 编码版本。

## 技术选型

| 层级 | 选型 | POC 实现 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite + Ant Design X | 已就绪（Bubble / Sender / Welcome） |
| 后端 | Python 3.11 + FastAPI，SSE 流式 | 已就绪 |
| 编排 | LangGraph StateGraph + StreamWriter custom（预处理 + 意图分类 + 四路分支） | 已就绪 |
| 模型 | 直连 DeepSeek / OpenAI 兼容，抽象成 `BaseChatModel` | 已就绪（含 mock 演示模式） |
| 短期记忆 | `MemorySaver`，`thread_id` 隔离 | 已就绪 |
| 工具调用 | POC 不向模型暴露工具；订单走确定性 query 节点 | 已就绪 |
| 简易 RAG | 进程内检索 + 50 篇电商 HTML + 引用 | 已就绪（HTML 按 h2 切块） |
| 订单查询 | JSON 演示数据（50 单，按 Postgres 表形状） | 已就绪（`#/orders`） |
| 知识库 | 50 篇 HTML 文章 + 分类/标签目录 | 已就绪（`#/kb`） |
| 工单存储 | JSON 文件（`backend/data/tickets.json`） | 已就绪 |
| 订单存储 | JSON 演示数据（字段按 Postgres 表形状） | 已就绪，`ORDER_STORE=postgres` 为升级开关 |
| 可观测性 | Langfuse v5 + LangChain CallbackHandler | 可选，默认关闭；支持 Cloud/自托管 |
| 部署 | 本地 uvicorn + `npm run dev`；Docker Compose 预留 | docker/ 目录已放好落点 |

四个扩展点（LLM / 工具 / 记忆 / 检索）都走工厂 + 配置，业务代码只依赖 LangChain 标准接口，
所以生产化替换只改 `.env`，不动业务代码。

## 快速开始

```powershell
conda activate qa-ticket
pip install -r requirements.txt

Copy-Item .env.example .env      # 什么都不填也能跑（演示模式）

# 命令行验收：能流式输出回答即通过
python -m backend.scripts.cli_chat --once "退款多久到账？"

# 订单查询：按收货人姓名/订单号直接查，不建工单
python -m backend.scripts.cli_chat --once "帮我查询张三的订单"

# 走一遍「知识库问答 → 订单查询 → 多轮追问」（演示模式下也能跑）
python -m backend.scripts.cli_chat
#   你 > 退款多久到账                          <- 知识库问答，带引用
#   你 > 帮我查询张三的订单                    <- 走确定性 query，不建单
#   你 > 那退款失败会怎么处理                  <- 多轮追问

# 后端：起 HTTP 服务（/docs 里有交互式接口文档）
uvicorn backend.api.app:app --reload --port 5179

# 前端：另开一个终端
cd frontend
npm install
npm run dev            # 打开 http://127.0.0.1:5173
```

现场演示想只开一个地址（也更稳，不依赖 Vite）：

```powershell
npm --prefix frontend run build        # 产出 frontend/dist
python -m uvicorn backend.api.app:app --port 5179
# 浏览器打开 http://127.0.0.1:5179/   ← 首页即前端；/docs 仍是接口文档
```

接真实模型：`.env` 里把 `LLM_PROVIDER` 改成 `deepseek`（或 `openai`），填 `LLM_API_KEY`，
`LLM_BASE_URL` 默认就是 `https://api.deepseek.com/v1`。

前端 dev server 与后端同机：页面只访问 `127.0.0.1:5173`，`/chat` 与 `/api` 通过 Vite 代理转到
`127.0.0.1:5179`（见 [frontend/vite.config.ts](frontend/vite.config.ts)）。浏览器始终同源，
所以 SSE 不受 CORS 约束，后端的 `CORS_ORIGINS` 只作为「绕过代理直连后端」的兜底。
想直连后端时，在前端目录建 `.env.local` 写 `VITE_API_BASE=http://127.0.0.1:5179` 即可。

## Langfuse 可观测性（可选）

在 `.env` 填入：

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

自托管时把 `LANGFUSE_BASE_URL` 改为自己的 Langfuse 地址。启用后，LangGraph 节点、LLM、
Retriever 调用会自动上报；`thread_id` 作为 session ID。初始化或上报失败不会影响问答主链路。

## 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/chat` | 统一流式对话入口（SSE），自动执行 LLM 意图识别并分流 |
| POST | `/branch/knowledge` | 强制进入知识库问答分支（SSE） |
| POST | `/branch/query` | 强制进入订单查询分支（SSE） |
| POST | `/branch/service` | 强制进入售后业务草稿分支（SSE） |
| POST | `/branch/service/confirm` | 用户确认后提交业务办理并创建售后工单 |
| POST | `/branch/fallback` | 强制进入兜底分支（SSE） |
| GET | `/health` | 健康检查，返回当前 provider 与各扩展点实现 |
| GET | `/api/agent-info` | 当前 Agent 能力（模型、工具、工单数、知识库文档/片段数、预留的 compose 落点） |
| GET | `/api/kb/search?q=&top_k=` | 知识库检索命中（来源、小节、片段、相关度），供右侧知识面板 |
| GET | `/api/kb/articles?q=&category=` | 知识库文章列表（目录/分类/关键字） |
| GET | `/api/kb/categories` | 知识库分类 |
| GET | `/api/metrics/summary?days=7` | 运营指标：Token、首字延迟、请求量、错误率、按意图明细 |
| GET | `/api/orders?q=&status=&user_id=` | 电商订单查询（50 条演示订单） |
| GET | `/kb/index.html`、`/kb/pages/*.html` | 知识库静态 HTML 页面（可直接浏览） |

所有对话接口共用 `start` / `intent` / `token` / `order` / `service_draft` /
`citation` / `done` / `error` 事件契约。业务草稿阶段只读；只有用户点击“确认提交”并
调用 `/branch/service/confirm` 后才创建售后工单。

SSE 生成器会在普通异常或 payload 序列化失败时记录日志，并以单个终止性 `error`
事件返回；客户端取消不会被误报为服务错误。

## 界面（5 个页面）

浅色 Codex 风格，hash 路由（静态托管零配置）：

| 地址 | 页面 | 内容 |
| --- | --- | --- |
| `#/` | 首页 | 只有对话框：居中输入框 + 快捷问题 + 底部版本号 |
| `#/chat` | 对话记录 | 左侧会话历史（今天/昨天/更早）+ 对话区，引用与订单标签渲染在气泡底部 |
| `#/chat?panel=knowledge` | 对话 + 知识库 | 右侧列出**这一轮**问答的 Top-K 检索命中（来源、小节、相关度、片段） |
| `#/chat?panel=orders` | 对话 + 订单 | 右侧显示**这一轮** query 分支查到的订单（单号/状态/金额/商品/收货人） |
| `#/chat?panel=service` | 对话 + 业务办理 | 右侧编辑槽位、查看缺失提醒，并在核对后确认提交 |
| `#/orders` | 订单查询 | 按订单号/用户/商品关键词 + 状态过滤；右侧查看明细、金额、支付/退款与状态时间线 |
| `#/kb` | 知识库检索 | 8 个分类浏览 50 篇 HTML；关键词检索 + RAG 命中片段，点击打开 HTML 原文 |
| `#/admin` | 后台管理 | Token 消耗、平均首字延迟、请求总量、错误率、意图调用明细 |

会话历史存在浏览器 localStorage（POC 不做服务端会话列表）；后台指标为进程内统计，重启清零。
页脚/侧栏显示当前 git 短 hash，方便对照改前/改后版本。

右侧面板按「轮次」绑定：新提问后面板自动切到新一轮（结果为空时不会残留上一轮的内容）；
点历史消息里的引用/订单/业务草稿标签，面板会切回那一轮的数据。业务办理必须先由用户核对并确认，
前端不会在生成草稿时自动创建工单。

## 对话路由（四路）

一轮对话在 LangGraph 里固定走：`preprocess → classify → 四路分支`。

| 意图 | HTTP 分支 | 判定（规则兜底） | 分支行为 | 前端事件 |
| --- | --- | --- | --- | --- |
| `knowledge` 知识咨询 | `POST /branch/knowledge` | 默认分支 | RAG 检索 + 生成回答 | `citation` + `token` |
| `query` 订单查询 | `POST /branch/query` | 订单号 / 我的订单 / 查订单 / 订单进度 | 查 `OrderService`，不检索 | `order` + `token` |
| `service` 业务办理 | `POST /branch/service` | 建单 / 退货 / 换货 / 维修 / 保修 / 质量问题 | 识别槽位、生成可编辑草稿并提示缺失项；确认后提交 | `service_draft` + `token` |
| `fallback` 兜底 | `POST /branch/fallback` | 投诉 / 转人工 / 问候 / 闲聊 | 兜底话术；演示版未接人工坐席 | `token` |

分类器优先用 LLM 结构化输出（`with_structured_output`），演示模式或分类失败时自动退回规则；
每次识别结果通过 `intent` 事件返回，对话页顶栏显示当前路由。`/chat` 负责自动分类；
`/branch/*` 则由 HTTP 路径直接锁定意图，便于联调、测试和后续按分支独立扩展。

业务办理槽位包括业务类型、订单号、联系人和问题描述。缺失项会在右侧高亮；
信息齐全后仍需勾选核对声明并点击“确认提交”，随后由 `/branch/service/confirm` 创建工单。

## 测试

```powershell
python -m pytest            # 84 个用例，约 8 秒
python -m pytest -v         # 看每个用例名
```

用例覆盖检索、工单存储、工具参数校验、LangGraph 编排、HTTP/SSE 接口与整链演示流程，
固定使用演示模式与临时数据目录，**不联网、不依赖外部服务、不污染项目数据**。
用例清单、边界用例与前端手工用例见 [docs/test-cases.md](docs/test-cases.md)。

## 结构图

```powershell
python -m backend.scripts.draw_graph --png --html
```

从运行时图导出（所以永远和 `build_graph()` 的实际结构一致）：终端 ASCII 图、`docs/graph.png`、
`docs/graph.mmd`（Mermaid 源）、`docs/graph.html`。
图上的节点与条件边标注由运行时结构和配置生成。
PNG 先试 mermaid.ink，失败就用本机 Chrome/Edge 离线渲染并裁掉空白（`--local` 可强制离线）。
在 Jupyter 里可以 `from IPython.display import Image, display; display(Image(graph.get_graph().draw_mermaid_png()))`，
细节见 [docs/architecture.md](docs/architecture.md)。

## 知识库与检索（RAG）

知识库是 `backend/data/demo/ecommerce/kb/pages/` 下的 50 篇电商帮助中心 HTML 页面
（下单支付、配送物流、退换售后、发票、会员、账户、商品、商家规则），
`articles.json` 是文章索引与分类，`index.html` 是可直接浏览的目录页。
检索器同时支持 `.md`、`.txt` 与 `.html`，HTML 按 `<h2>` 切块、去标签后参与打分。

电商订单与知识库数据由固定种子的生成器产出：

```powershell
python -m backend.scripts.generate_ecommerce_demo
```

数据说明见 [docs/ecommerce-demo-data.md](docs/ecommerce-demo-data.md)；Postgres 目标结构见
[docs/sql/postgres_schema.sql](docs/sql/postgres_schema.sql)（订单 8 表 + 知识库 7 表）。

检索实现（[backend/infrastructure/retrieval/in_memory.py](backend/infrastructure/retrieval/in_memory.py)）刻意做成零依赖、可解释：

1. Markdown 按 `##` 切小节；HTML 按 `<h2>` 切块并去掉标签；
2. 查询与片段都按「英文单词 + 中文二元组」切词；
3. 用查询词与片段的关键词命中数打分，标题命中额外加权，取 `RAG_TOP_K`（默认 3）条；
4. 至少命中 1 个有效查询词才视为召回；否则不注入资料。

命中的片段以 `【参考资料】` 块拼进系统提示，同时把出处通过 `citation` 事件回传前端，
回答里标 `[1][2]` 对应片段。参考资料**不进消息历史**，所以多轮对话不会被旧资料撑爆。

这套关键词检索的短板很直接：换个说法（同义词）就可能检不到，长问题也容易被高频词带偏。
生产环境换成「向量检索 + 关键词混合 + 重排」，只要实现 LangChain 的 `BaseRetriever`
并把 `.env` 改成 `RETRIEVER=pgvector`，`graph.py` 与工具层都不用动。

## 目录结构

```
backend/
  domain/              领域层：工单实体（models.py）、业务规则（rules.py）、领域异常（errors.py）
  application/         应用层
    runtime.py         装配：调工厂拼出运行时（不含业务动作）
    agent/             graph.py（意图、提示词与四路编排）
    chat/service.py    用例：一轮对话（驱动图 + 翻译 token/order/service_draft/citation 事件）
    contracts/         跨 Agent/Chat/API 的对话事件契约（EVENT_*）
    tickets/service.py 用例：确认后创建工单与计数
    orders/service.py  用例：电商订单查询
    knowledge/service.py 用例：知识库目录浏览/搜索
  infrastructure/      基础设施层
    config.py          集中配置，决定用哪个实现
    logging.py         日志初始化（手写 Handler，避免 basicConfig 静默失效）
    llm/               模型工厂 + 演示模式假模型
    memory/            短期记忆（checkpointer）工厂
    retrieval/         进程内检索（切块 + 关键词命中打分 + 拼参考资料）
    persistence/       store.py：工单/订单 JSON 存储、知识库目录与工厂
    llm/ memory/ retrieval/  各包的 __init__.py 集成实现与工厂
    observability/     进程内指标 + 可选 Langfuse tracing
  api/                 接口层
    app.py             FastAPI 组装（中间件、路由注册、静态托管、生命周期）
    deps.py            依赖取用点（从 app.state 取运行时与用例）
    streaming.py       SSE 响应封装（/chat 与 /branch/* 共用）
    routes/            dialogue.py / service.py / resources.py / system.py
    schemas.py         请求响应模型与 SSE 编码
  scripts/cli_chat.py  命令行验收
  scripts/draw_graph.py 导出 LangGraph 结构图（ASCII / Mermaid / PNG）
  data/tickets.json    工单落盘位置（自动生成，不进版本库）
  data/demo/ecommerce/ 50 条订单 + 50 篇 HTML 知识库（含 tables/ 与 kb/）
frontend/
  vite.config.ts       代理到后端 + 固定 127.0.0.1（避开 localhost→::1 连不上的坑）
  src/main.tsx         React 挂载 + 浅色主题 token + antd 中文 locale + XProvider
  src/router.ts        hash 路由（#/、#/chat、#/orders、#/kb、#/admin）
  src/App.tsx          路由分发 + 后端信息 + 离线提示
  src/pages/           HomePage / ChatPage / OrdersPage / KnowledgePage / AdminPage
  src/components/      Sidebar / Composer / MessageList / KnowledgePanel / OrderPanel / ServicePanel
                       / KpiCard / VersionBadge / SiteSidebar
  src/hooks/           useChat（流式与会话恢复）、useConversations（localStorage 历史）
  src/api/agent.ts     API 层：streamChat() 手写 SSE 解析 + 工单/知识库/指标查询
  src/types.ts         与后端 schemas.py 对应的类型
docs/
  architecture.md      架构图、执行路径、SSE 事件表、扩展点与生产替换
  demo-script.md       3 分钟演示分镜、准备清单、兜底预案
  interview-notes.md   30 秒陈述与高频追问应对
  deployment.md        三种跑法、compose 升级步骤、日志与排查
  test-cases.md        50 个自动化用例 + 11 个前端手工用例 + 需求覆盖矩阵
docker/                compose 升级落点（POC 不启用）
```

对话路由的装配层级：

```text
app
├── dialogue aggregator
│   ├── chat router
│   │   └── POST /chat
│   └── intent-branches router
│       ├── POST /branch/knowledge
│       ├── POST /branch/query
│       ├── POST /branch/service
│       └── POST /branch/fallback
└── service-actions router
    └── POST /branch/service/confirm
```

## 排期

| 阶段 | 内容 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| 1 | 工程搭建 + LangGraph 最小图 | 命令行流式输出模型回答 | 已完成 |
| 2 | 工具 + 短期记忆 + 工厂 | 多轮不丢上下文，工具可被调用，工单落 JSON | 已完成 |
| 3 | 前端 Ant Design X | 页面能输入、流式显示、多轮对话 | 已完成 |
| 4 | 简易 RAG + 引用 | 基于知识库作答并显示引用 | 已完成 |
| 5 | 联调 + README + 演示脚本 | 端到端可演示，含话术 | 已完成 |

## 生产化升级路径（POC 只预留，不实现）

| 现在 | 换成 | 改哪里 |
| --- | --- | --- |
| `MemorySaver` | `PostgresSaver` | `.env: CHECKPOINTER=postgres` |
| 进程内检索 | pgvector / Qdrant | `.env: RETRIEVER=pgvector` |
| JSON 工单文件 | Postgres 工单表 | `.env: TICKET_STORE=postgres` |
| 直连模型 | LiteLLM 网关 | `infrastructure/llm/__init__.py` 加一个分支 |
| ~~`logging.basicConfig`~~ | 已落地：手写 `Handler` + 判断注册 | `infrastructure/logging.py` |
| 单进程 | Docker Compose | 打开 `docker/docker-compose.yml` 注释块 |

关于日志这条，升级时要带两个保护：`if logger.handlers: return`——判断的是**要挂 handler 的那个 logger**，不是 root（`basicConfig` 恰好判 root，所以 root 一旦被 uvicorn / pytest 配过，它会静默失效）；命名 logger 自己挂了 handler 之后要设 `propagate = False`，否则 root 上的 handler 会把同一条日志再打一遍。配置要分开发/生产两套时，`dictConfig` + `disable_existing_loggers: False` 比手写更好维护。

权限（RBAC）、Redis 缓存、异步任务、监控告警属于生产化范围，POC 不落代码。
