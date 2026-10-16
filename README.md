# 企业IT服务台 智能问答工单 Agent POC

用一句话说清楚这件事：员工用日常语言描述问题 → Agent 先查知识库给答案并标出处 →
知识库解决不了或用户明确要求时，自动整理字段建工单 → 之后能查进度、补信息、转人工。

> 状态：阶段一（工程搭建 + LangGraph 最小图）已完成，其余阶段按下面排期推进。

## 技术选型

| 层级 | 选型 | POC 实现 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite + Ant Design X | 阶段三 |
| 后端 | Python 3.11 + FastAPI，SSE 流式 | 已就绪 |
| 编排 | LangGraph StateGraph（只实现 Agent + Tool 两分支） | 已就绪 |
| 模型 | 直连 DeepSeek / OpenAI 兼容，抽象成 `BaseChatModel` | 已就绪（含 mock 演示模式） |
| 短期记忆 | `MemorySaver`，`thread_id` 隔离 | 阶段二 |
| 工具调用 | `create_ticket` / `query_ticket` / `escalate_to_human` | 阶段二 |
| 简易 RAG | 进程内检索 + 3~5 篇文档 + 引用 | 阶段四 |
| 工单存储 | JSON 文件（内存态 + 落盘） | 阶段二 |
| 部署 | 本地 uvicorn + `npm run dev`；Docker Compose 预留 | docker/ 目录已放好落点 |

四个扩展点（LLM / 工具 / 记忆 / 检索）都走工厂 + 配置，业务代码只依赖 LangChain 标准接口，
所以生产化替换只改 `.env`，不动业务代码。

## 快速开始（阶段一）

```powershell
conda activate qa-ticket
pip install -r requirements.txt

Copy-Item .env.example .env      # 什么都不填也能跑（演示模式）

# 命令行验收：能流式输出回答即通过
python -m backend.scripts.cli_chat --once "VPN 连不上怎么办"

# 起 HTTP 服务：/docs 里有交互式接口文档
uvicorn backend.main:app --reload --port 5179
```

接真实模型：`.env` 里把 `LLM_PROVIDER` 改成 `deepseek`（或 `openai`），填 `LLM_API_KEY`，
`LLM_BASE_URL` 默认就是 `https://api.deepseek.com/v1`。

## 目录结构

```
backend/
  config.py            集中配置，决定用哪个实现
  graph.py             LangGraph 编排（Agent + Tool，预留 P-E-V-S 扩展）
  tools.py             工具注册表（阶段二填内容）
  schemas.py           SSE 事件与请求体定义
  runtime.py           装配层 + 统一流式出口
  main.py              FastAPI + SSE 接口
  factories/llm.py     模型工厂
  mock_llm.py          演示模式假模型
  scripts/cli_chat.py  命令行验收
  data/kb/             阶段四的知识库文档
docker/                compose 升级落点（POC 不启用）
```

## 排期

| 阶段 | 内容 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| 1 | 工程搭建 + LangGraph 最小图 | 命令行流式输出模型回答 | 已完成 |
| 2 | 工具 + 短期记忆 + 工厂 | 多轮不丢上下文，工具可被调用，工单落 JSON | 待办 |
| 3 | 前端 Ant Design X | 页面能输入、流式显示、多轮对话 | 待办 |
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
