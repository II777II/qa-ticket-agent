"""Domain models and deterministic business rules."""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, computed_field

ORDER_NO_RE = re.compile(r"SO\d{12}", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
IntentName = Literal["read", "write", "human"]
ServiceType = Literal["退货", "换货", "维修", "退款", "补发", "价保", "其他"]
TicketCategory = Literal[
    "订单与支付", "配送与物流", "退换与售后", "发票与报销",
    "商品与质量", "账户与安全", "其他",
]
TicketPriority = Literal["紧急", "高", "中", "低"]
ORDER_LOOKUP_HINTS = (
    "我的订单", "查订单", "查询订单", "订单查询", "订单进度", "订单状态",
    "订单到哪", "查一下订单", "订单号", "订单怎么样",
)
ORDER_LOOKUP_VERBS = ("查询", "查一下", "查下", "查", "查看", "看下", "进度", "状态", "到哪", "我的", "我要", "给我")
KNOWLEDGE_EXCLUSIONS = ("退款", "退货", "发票", "物流", "发货", "规则", "流程", "怎么开", "如何开")
CREATE_HINTS = ("建单", "建个工单", "创建工单", "提交工单", "售后工单", "帮我建", "帮我提")
WRITE_HINTS = ("申请退货", "申请换货", "申请维修", "申请退款", "办理退货", "办理换货", "办理维修", "帮我退", "帮我换", "帮我维修", "我要退", "我要换", "我要维修", "需要维修", "需要换货")
HUMAN_HINTS = ("投诉", "差评", "转人工", "人工客服", "找人工", "客服电话")
CHAT_HINTS = ("在吗", "你好", "您好", "嗨", "谢谢", "闲聊")
SERVICE_TYPE_RULES: tuple[tuple[ServiceType, tuple[str, ...]], ...] = (
    ("换货", ("换货", "换新")), ("退货", ("退货", "退掉")), ("维修", ("维修", "保修")),
    ("退款", ("退款", "退钱")), ("补发", ("补发", "重发")), ("价保", ("价保", "保价")),
)
ORDER_STATUS_LABELS = {
    0: "待支付", 10: "已支付", 20: "待发货", 30: "已发货",
    40: "已完成", 50: "已取消", 60: "退款中", 70: "已退款",
}
PAY_STATUS_LABELS = {0: "未支付", 1: "已支付", 2: "部分退款", 3: "全额退款"}
SOURCE_LABELS = {1: "APP", 2: "小程序", 3: "H5"}


class IntentResult(BaseModel):
    intent: IntentName
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""
    slots: dict[str, str] = Field(default_factory=dict)


def extract_order_keyword(text: str) -> str:
    cleaned = text
    for hint in (
        "帮我查询", "帮我查一下", "帮忙查询", "帮我查", "帮我查看", "查看一下", "查看",
        "看一下", "看下", "查询一下", "查询", "查一下", "查下", "查", "我要", "给我",
        "我的订单", "订单进度", "订单状态", "订单到哪了", "订单", "一下", "请问",
    ):
        cleaned = cleaned.replace(hint, "")
    return (re.sub(r"[，,。；;、！!？?：:\s的]+", " ", cleaned).strip() or text)[:30]


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
    return bool(ORDER_NO_RE.search(text)) or any(hint in text for hint in ORDER_LOOKUP_HINTS) or (
        "订单" in text and any(verb in text for verb in ORDER_LOOKUP_VERBS) and not any(word in text for word in KNOWLEDGE_EXCLUSIONS)
    )


def rule_classify(text: str) -> IntentResult:
    order_query = is_order_query(text)
    write_request = any(hint in text for hint in CREATE_HINTS + WRITE_HINTS)
    if any(word in text for word in HUMAN_HINTS) or (
        len(text.strip()) <= 12 and any(word in text for word in CHAT_HINTS) and not order_query and not write_request
    ):
        return IntentResult(intent="human", confidence=0.9, reason="命中投诉/转人工/闲聊规则")
    if write_request:
        return IntentResult(intent="write", confidence=0.9, reason="命中售后业务动作", slots=extract_service_slots(text))
    if order_query:
        order_no = ORDER_NO_RE.search(text)
        slots = {"order_no": order_no.group(0).upper()} if order_no else {"keyword": extract_order_keyword(text)}
        return IntentResult(intent="read", confidence=0.85, reason="只读请求，规则选择订单查询工具", slots=slots)
    return IntentResult(intent="read", confidence=0.75, reason="只读请求，规则选择知识库工具")


class KnowledgeArticle(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    article_no: str
    title: str
    summary: str = ""
    category_id: int
    category_code: str
    category_name: str
    tags: list[str] = Field(default_factory=list)
    is_top: int = 0
    sort_weight: int = 0
    path: str
    url: str


class KnowledgeCategory(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    name: str
    code: str
    sort_no: int = 0


class OrderRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    order_no: str
    user_id: int
    order_status: int
    pay_status: int
    source: int
    payable_amount: float
    paid_amount: float = 0
    refund_amount: float = 0
    created_at: str
    user: dict | None = None
    items: list[dict] = Field(default_factory=list)

    @computed_field
    @property
    def status_label(self) -> str:
        return ORDER_STATUS_LABELS.get(self.order_status, "未知状态")

    @computed_field
    @property
    def pay_status_label(self) -> str:
        return PAY_STATUS_LABELS.get(self.pay_status, "未知")

    @computed_field
    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, "未知")

    def summary(self) -> dict:
        return {
            "order_no": self.order_no, "status": self.status_label, "pay_status": self.pay_status_label,
            "customer": (self.user or {}).get("name") or self.user_id,
            "payable_amount": self.payable_amount, "paid_amount": self.paid_amount,
            "refund_amount": self.refund_amount, "created_at": self.created_at,
            "items": [
                {
                    "name": item.get("product_name", ""), "spec": item.get("sku_spec"),
                    "quantity": item.get("quantity", 0), "price": item.get("price", 0),
                }
                for item in self.items
            ],
        }


class TicketCreate(BaseModel):
    title: str = Field(min_length=4, max_length=60)
    description: str = Field(min_length=10)
    category: TicketCategory
    priority: TicketPriority
    contact: str = Field(min_length=2)


class TicketRecord(TicketCreate):
    id: str
    status: str = "待受理"
    created_at: str


def next_ticket_id(existing_ids: Iterable[str], today: date | None = None) -> str:
    prefix = f"TK-{(today or date.today()):%Y%m%d}-"
    used = [int(tail) for item in existing_ids if item.startswith(prefix) and (tail := item.rsplit("-", 1)[-1]).isdigit()]
    return f"{prefix}{max(used) + 1 if used else 1:04d}"


def duplicate_of(existing: Sequence[TicketRecord], payload: TicketCreate) -> TicketRecord | None:
    contact, title = payload.contact.strip().lower(), payload.title.strip()
    return next(
        (item for item in existing if item.contact.strip().lower() == contact and item.title.strip() == title),
        None,
    )
