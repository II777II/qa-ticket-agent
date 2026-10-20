"""对话意图的规则识别。

POC 先用关键词/订单号规则，保证演示模式（无模型 Key）也能路由；
将来换 LLM 结构化分类器时，只要保持 `detect_intent()` 的返回值不变。

返回值：
    order_lookup  查订单（走 query_order，跳过 RAG）
    after_sales   售后处理（可建售后工单）
    knowledge     帮助中心问答（走 RAG）
"""

from __future__ import annotations

import re

ORDER_NO_RE = re.compile(r"SO\d{12}", re.IGNORECASE)

ORDER_LOOKUP_HINTS = (
    "我的订单", "查订单", "查询订单", "订单查询", "订单进度", "订单状态",
    "订单到哪", "查一下订单", "订单号", "订单怎么样",
)

ORDER_LOOKUP_VERBS = ("查询", "查一下", "查下", "查", "查看", "看下", "进度", "状态", "到哪", "我的")
# 这些词说明用户问的是规则/售后，而不是查具体订单
KNOWLEDGE_EXCLUSIONS = ("退款", "退货", "发票", "物流", "发货", "规则", "流程", "怎么开", "如何开")

CREATE_HINTS = ("建单", "建个工单", "创建工单", "提交工单", "售后工单", "帮我建", "帮我提")
AFTER_SALES_HINTS = ("退货", "换货", "维修", "保修", "价保", "质量问题", "退款失败", "没收到", "损坏")


def detect_intent(text: str) -> str:
    mentions_order = "订单" in text
    asks_lookup = any(verb in text for verb in ORDER_LOOKUP_VERBS)
    excludes = any(word in text for word in KNOWLEDGE_EXCLUSIONS)
    if (
        ORDER_NO_RE.search(text)
        or any(hint in text for hint in ORDER_LOOKUP_HINTS)
        or (mentions_order and asks_lookup and not excludes)
    ):
        return "order_lookup"
    if any(hint in text for hint in CREATE_HINTS) or any(hint in text for hint in AFTER_SALES_HINTS):
        return "after_sales"
    return "knowledge"
