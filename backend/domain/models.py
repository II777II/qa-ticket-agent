"""Domain entities and deterministic order/ticket rules."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, computed_field

ServiceType = Literal["退货", "换货", "维修", "退款", "补发", "价保", "其他"]
TicketCategory = Literal[
    "订单与支付", "配送与物流", "退换与售后", "发票与报销",
    "商品与质量", "账户与安全", "其他",
]
TicketPriority = Literal["紧急", "高", "中", "低"]
ORDER_STATUS_LABELS = {
    0: "待支付", 10: "已支付", 20: "待发货", 30: "已发货",
    40: "已完成", 50: "已取消", 60: "退款中", 70: "已退款",
}
PAY_STATUS_LABELS = {0: "未支付", 1: "已支付", 2: "部分退款", 3: "全额退款"}
SOURCE_LABELS = {1: "APP", 2: "小程序", 3: "H5"}


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
            "order_no": self.order_no,
            "status": self.status_label,
            "pay_status": self.pay_status_label,
            "customer": (self.user or {}).get("name") or self.user_id,
            "payable_amount": self.payable_amount,
            "paid_amount": self.paid_amount,
            "refund_amount": self.refund_amount,
            "created_at": self.created_at,
            "items": [
                {
                    "name": item.get("product_name", ""),
                    "spec": item.get("sku_spec"),
                    "quantity": item.get("quantity", 0),
                    "price": item.get("price", 0),
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
    used = [
        int(tail)
        for item in existing_ids
        if item.startswith(prefix) and (tail := item.rsplit("-", 1)[-1]).isdigit()
    ]
    return f"{prefix}{max(used) + 1 if used else 1:04d}"


def duplicate_of(existing: Sequence[TicketRecord], payload: TicketCreate) -> TicketRecord | None:
    contact, title = payload.contact.strip().lower(), payload.title.strip()
    return next(
        (
            item for item in existing
            if item.contact.strip().lower() == contact and item.title.strip() == title
        ),
        None,
    )
