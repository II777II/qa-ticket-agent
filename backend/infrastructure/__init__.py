"""基础设施层：外部依赖的具体实现与装配件。

    config.py       集中配置（所有可替换开关都在这里）
    llm/            模型工厂 + 演示模式实现
    memory/         LangGraph 检查点（短期记忆）工厂
    retrieval/      检索实现与工厂
    persistence/    工单存储实现与工厂

这一层实现领域层/应用层用到的 LangChain 抽象接口（BaseChatModel、BaseRetriever、
BaseCheckpointSaver）与存储协议，所以它才是「可替换点」：
换 Postgres、pgvector、LiteLLM 都只动这里。
"""
