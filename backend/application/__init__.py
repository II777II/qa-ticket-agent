"""应用层：用例编排与运行时装配。

    runtime.py          装配层：调工厂把 LLM/工具/检索/记忆/存储拼成运行时（不含业务动作）
    agent/              Agent 编排关注点：graph（LangGraph 图）、tools（工具适配）、prompts（提示词）
    chat/service.py     用例：一轮对话（驱动图 + 翻译事件）
    tickets/service.py  用例：工单动作（建单、催单、转人工）

依赖方向：api → application → domain；infrastructure 由 application 在装配时注入。
"""
