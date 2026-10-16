"""问答工单 Agent POC - 后端包。

分层约定（业务代码只依赖抽象，不依赖具体实现）：
    config.py        集中配置，决定用哪个实现
    factories/       工厂：按配置创建 LLM / Checkpointer / Retriever / 工单存储
    graph.py         LangGraph 编排（POC 只实现 Agent + Tool 两分支）
    tools.py         工具注册表
    stores/          工单存储实现
    retrievers/      检索实现
    runtime.py       装配层 + 统一流式出口
    main.py          HTTP/SSE 接口
"""
