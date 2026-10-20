"""对话事件词表——应用层与接口层之间的契约。

    start     一轮开始（带模型名与是否演示模式）
    intent    意图识别结果（意图/置信度/原因/槽位）
    token     模型输出增量
    tool      工具调用与返回
    ticket    产生或查到的工单
    order     查到的订单（query_order 结果）
    service_draft 业务办理草稿与缺失槽位
    citation  检索引用
    done      一轮结束
    error     出错

应用层负责产生它们，接口层负责编码成 SSE（`api/schemas.py` 的 `sse()`），
CLI 与前端按事件名分发。加能力 = 加事件名，不动接口形状。
"""

from __future__ import annotations

EVENT_START = "start"
EVENT_INTENT = "intent"
EVENT_TOKEN = "token"
EVENT_TOOL = "tool"
EVENT_CITATION = "citation"
EVENT_TICKET = "ticket"
EVENT_ORDER = "order"
EVENT_SERVICE_DRAFT = "service_draft"
EVENT_DONE = "done"
EVENT_ERROR = "error"
