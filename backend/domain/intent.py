"""Read/write/human intent classification and slot extraction."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from backend.domain.models import ServiceType, TicketCategory

ORDER_NO_RE = re.compile(r"SO\d{12}", re.I)
USER_ID_RE = re.compile(r"(?:user[_\s-]?id|用户\s*(?:id|编号)?)\s*[:：=]?\s*(\d{3,})", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
IntentName = Literal["read", "write", "human"]
CREATE_HINTS = ("建单", "建个工单", "创建工单", "提交工单", "售后工单", "帮我建", "帮我提")
WRITE_HINTS = (
    "申请退货", "申请换货", "申请维修", "申请退款", "申请补发", "申请价保",
    "办理退货", "办理换货", "办理维修", "帮我退", "帮我换", "帮我维修",
    "我要退", "我要换", "我要维修", "需要维修", "需要换货",
)
HUMAN_HINTS = ("投诉", "差评", "转人工", "人工客服", "找人工", "客服电话")
CHAT_HINTS = ("在吗", "你好", "您好", "嗨", "谢谢", "闲聊")
SERVICE_TYPE_RULES: tuple[tuple[ServiceType, tuple[str, ...]], ...] = (
    ("换货", ("换货", "换新")), ("退货", ("退货", "退掉")), ("维修", ("维修", "保修")),
    ("退款", ("退款", "退钱")), ("补发", ("补发", "重发")), ("价保", ("价保", "保价")),
)


class IntentResult(BaseModel):
    intent: IntentName
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""
    slots: dict[str, str] = Field(default_factory=dict)


def guess_category(text: str) -> TicketCategory:
    rules = (
        ("退换与售后", ("退货", "换货", "维修", "保修", "价保")),
        ("配送与物流", ("物流", "发货", "快递", "签收", "配送", "收货地址", "到货", "包裹")),
        ("发票与报销", ("发票", "开票", "报销", "税号", "专票")),
        ("账户与安全", ("账号", "密码", "登录", "安全", "绑定", "注销")),
        ("订单与支付", ("订单", "支付", "付款", "退款", "下单", "优惠券", "运费", "取消")),
        ("商品与质量", ("商品", "质量", "损坏", "规格", "型号", "驱动", "安装", "配件", "打印机")),
    )
    best = max(rules, key=lambda item: sum(word in text for word in item[1]))
    return best[0] if any(word in text for word in best[1]) else "其他"


def extract_service_slots(text: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    if order := ORDER_NO_RE.search(text):
        slots["order_no"] = order.group(0).upper()
    if contact := EMAIL_RE.search(text) or PHONE_RE.search(text):
        slots["contact"] = contact.group(0)
    for service_type, hints in SERVICE_TYPE_RULES:
        if any(hint in text for hint in hints):
            slots["service_type"] = service_type
            break
    slots["category"] = guess_category(text)
    return slots


def is_order_query(text: str) -> bool:
    return bool(ORDER_NO_RE.search(text) or USER_ID_RE.search(text))


def extract_user_id(text: str) -> int | None:
    return int(match.group(1)) if (match := USER_ID_RE.search(text)) else None


def rule_classify(text: str) -> IntentResult:
    order_query = is_order_query(text)
    write_request = any(hint in text for hint in CREATE_HINTS + WRITE_HINTS)
    if any(word in text for word in HUMAN_HINTS) or (
        len(text.strip()) <= 12
        and any(word in text for word in CHAT_HINTS)
        and not order_query
        and not write_request
    ):
        return IntentResult(intent="human", confidence=0.9, reason="命中投诉/转人工/闲聊规则")
    if write_request:
        return IntentResult(
            intent="write",
            confidence=0.9,
            reason="命中售后业务动作",
            slots=extract_service_slots(text),
        )
    if order_query:
        order_no = ORDER_NO_RE.search(text)
        slots = (
            {"order_no": order_no.group(0).upper()}
            if order_no else {"user_id": str(extract_user_id(text))}
        )
        return IntentResult(
            intent="read",
            confidence=0.85,
            reason="只读请求，规则选择订单查询工具",
            slots=slots,
        )
    return IntentResult(intent="read", confidence=0.75, reason="只读请求，规则选择知识库工具")
