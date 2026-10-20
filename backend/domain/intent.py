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
from typing import Literal

from pydantic import BaseModel, Field

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
FALLBACK_HINTS = ("投诉", "差评", "转人工", "人工客服", "客服电话", "在吗", "你好", "您好", "嗨", "谢谢", "闲聊")

IntentName = Literal["knowledge", "query", "service", "fallback"]


class IntentResult(BaseModel):
    """意图识别结果（LLM 结构化输出与规则兜底共用）。"""

    intent: IntentName = Field(description="knowledge=知识咨询, query=订单查询, service=售后业务办理, fallback=投诉/闲聊/转人工")
    confidence: float = Field(default=0.5, ge=0, le=1, description="置信度 0-1")
    reason: str = Field(default="", description="一句话说明判断依据")
    slots: dict[str, str] = Field(default_factory=dict, description="抽取到的槽位，如 order_no/keyword")


def extract_order_keyword(text: str) -> str:
    """从「帮我查询张三的订单」里抽出查询词（张三）。"""
    cleaned = text
    for hint in (
        "帮我查询", "帮我查一下", "帮忙查询", "帮我查", "查询一下", "查询", "查一下", "查下", "查",
        "我的订单", "订单进度", "订单状态", "订单到哪了", "订单", "一下", "请问",
    ):
        cleaned = cleaned.replace(hint, "")
    cleaned = re.sub(r"[，,。；;、！!？?：:\s的]+", " ", cleaned).strip()
    return (cleaned or text)[:30]


def guess_category(text: str) -> str:
    """售后工单草稿分类（电商 7 类）。"""
    rules = (
        ("退换与售后", ("退货", "换货", "维修", "保修", "价保")),
        ("配送与物流", ("物流", "发货", "快递", "签收", "配送", "收货地址", "到货", "包裹")),
        ("发票与报销", ("发票", "开票", "报销", "税号", "专票")),
        ("账户与安全", ("账号", "密码", "登录", "安全", "绑定", "注销")),
        ("订单与支付", ("订单", "支付", "付款", "退款", "下单", "优惠券", "运费", "取消")),
        ("商品与质量", ("商品", "质量", "损坏", "规格", "型号", "驱动", "安装", "配件", "打印机")),
    )
    best_category, best_score = "其他", 0
    for category, keywords in rules:
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_category, best_score = category, score
    return best_category


def detect_intent(text: str) -> str:
    """兼容旧接口：order_lookup / after_sales / knowledge。"""
    result = rule_classify(text)
    return {"query": "order_lookup", "service": "after_sales"}.get(result.intent, result.intent)


def rule_classify(text: str) -> IntentResult:
    """无模型/模型失败时的规则兜底。"""
    mentions_order = "订单" in text
    asks_lookup = any(verb in text for verb in ORDER_LOOKUP_VERBS)
    excludes = any(word in text for word in KNOWLEDGE_EXCLUSIONS)
    order_no = ORDER_NO_RE.search(text)
    if (
        order_no
        or any(hint in text for hint in ORDER_LOOKUP_HINTS)
        or (mentions_order and asks_lookup and not excludes)
    ):
        slots = {"order_no": order_no.group(0).upper()} if order_no else {"keyword": extract_order_keyword(text)}
        return IntentResult(intent="query", confidence=0.9, reason="命中订单查询关键词/订单号", slots=slots)
    if any(hint in text for hint in CREATE_HINTS) or any(hint in text for hint in AFTER_SALES_HINTS):
        return IntentResult(
            intent="service",
            confidence=0.85,
            reason="命中售后/业务办理关键词",
            slots={"category": guess_category(text)},
        )
    if any(hint in text for hint in FALLBACK_HINTS):
        return IntentResult(intent="fallback", confidence=0.8, reason="投诉/闲聊/转人工")
    return IntentResult(intent="knowledge", confidence=0.6, reason="默认走知识库问答")
