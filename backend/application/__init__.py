"""应用层：用例编排与运行时装配。

    runtime.py          装配层：调工厂把 LLM/工具/检索/记忆/存储拼成运行时（不含业务动作）
    agent/              LangGraph 图与四路业务编排
    chat/service.py     用例：一轮对话（驱动图 + 翻译事件）
    contracts/          应用层与接口适配器共享的对话事件契约
    tickets/service.py  用例：确认后创建工单与计数

依赖方向：api → application → domain；infrastructure 由 application 在装配时注入。
"""
