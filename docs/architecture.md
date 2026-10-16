# 架构与执行路径

## 整体结构

```mermaid
flowchart TD
    U[员工提问] --> FE[React + Ant Design X Bubble / Sender / ThoughtChain]
    FE -->|POST /chat SSE| API[FastAPI 胶水层 main.py]
    API --> RT[AgentRuntime runtime.py]
    RT --> G[LangGraph StateGraph graph.py]
    G --> A[agent 节点]
    A -->|有 tool_calls| T[tools 节点 ToolNode]
    T --> A
    A -->|无 tool_calls| E[END]
    KB[(知识库 backend/data/kb)] --> R[InMemoryRetriever]
    R --> A
    A -.->|retrieved| RT
    T -.->|ToolMessage| RT
    RT -->|token / tool / ticket / citation| FE
    CP[(MemorySaver thread_id 隔离)] --- G
    ST[(工单存储 JSON / Postgres)] --- T
```

## 分层与职责

| 层 | 文件 | 职责 | 换实现的代价 |
| --- | --- | --- | --- |
| 配置 | `backend/config.py` | 所有开关集中在这里，业务代码不读环境变量 | 无 |
| 工厂 | `backend/factories/*` | 按配置创建 LLM / 记忆 / 检索 / 工单存储 | 只加一个分支 |
| 编排 | `backend/graph.py` | 状态、节点、条件边、检索注入、系统提示词 | 不改 |
| 工具 | `backend/tools.py` | 三个 `@tool`，参数走 Pydantic 校验 | 不改 |
| 存储 | `backend/stores/json_store.py` | 工单落盘、时间线、重复建单拦截 | 新写一个实现 |
| 检索 | `backend/retrievers/memory.py` | 切块、打分、拼参考资料 | 新写一个实现 |
| 装配 | `backend/runtime.py` | 拼装组件 + 唯一流式出口 | 只改这一个文件 |
| 接口 | `backend/main.py` | HTTP/SSE、工单接口、可选同源托管前端 | 不改 |
| 前端 | `frontend/src/*` | 对话界面、工单面板、SSE 客户端 | 只改 `api/agent.ts` |

## 一轮对话的执行路径

1. 前端 `streamChat()` 发 `POST /chat`，带 `message` 与 `thread_id`；
2. `runtime.stream()` 以 `stream_mode=["messages", "updates"]` 订阅图；
3. `agent` 节点：用最后一条用户消息检索知识库，命中则把 `【参考资料】` 拼进系统提示，再 `llm.bind_tools(tools).invoke()`；
4. 条件边判断：有 `tool_calls` 就走 `tools` 节点执行，回到 `agent` 重新总结；没有就 `END`；
5. 过程中向前端推事件：

| 事件 | 时机 | 载荷 |
| --- | --- | --- |
| `start` | 收到请求 | `thread_id` / `provider` / `mock` |
| `token` | 模型流式增量 | `text` |
| `tool` | 工具被调用 / 返回 | `phase=call\|result`、`name`、`ok`、`message` |
| `ticket` | 工具产出工单 | `tickets[]`（完整工单） |
| `citation` | 本轮检索命中 | `index` / `source` / `title` / `snippet` / `score` |
| `done` / `error` | 一轮结束 | —— |

6. `MemorySaver` 按 `thread_id` 保存状态，多轮对话不丢上下文；
7. 前端把 `tool` 事件渲染成 ThoughtChain，把 `ticket` / `citation` 渲染成气泡底部的工单标签与引用；
8. 工单有变化时前端重新拉 `/api/tickets` 刷新右侧看板。

## 四个扩展点与生产替换

| 扩展点 | POC 实现 | 抽象接口 | 生产替换 | 怎么换 |
| --- | --- | --- | --- | --- |
| 模型 | `ChatOpenAI` 直连 DeepSeek / mock | `BaseChatModel` | LiteLLM 网关 / vLLM | `factories/llm.py` 加分支 |
| 记忆 | `InMemorySaver`（进程内存） | `BaseCheckpointSaver` | `PostgresSaver` | `.env: CHECKPOINTER=postgres` |
| 检索 | 关键词 IDF 打分 | `BaseRetriever` | pgvector + 混合检索 + 重排 | `.env: RETRIEVER=pgvector` |
| 工单存储 | JSON 文件 | 同名方法 | Postgres 工单表 | `.env: TICKET_STORE=postgres` |
| 前端 API | `streamChat()` fetch + SSE | `api/agent.ts` | useStream / WebSocket | 只改这一个文件 |
| 编排 | Agent + Tool 两节点 | LangGraph StateGraph | Planner/Executor/Validator/Summarizer | 加节点与条件边，现有节点不动 |

## 几个刻意的设计取舍

- **胶水层薄**：FastAPI 只做 HTTP/SSE 适配，编排全在 LangGraph，同一张图可以搬到 CLI、定时任务或消息网关。
- **查询与写入分离**：检索只读知识库，工具只写工单存储，互不碰对方的数据结构。
- **参考资料不进消息历史**：每轮临时拼进系统提示，多轮对话不会被旧资料撑爆上下文。
- **事件名即契约**：SSE 事件名固定 7 类，前端按名字分发，加能力只加事件不加接口。
