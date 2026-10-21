"""电商订单领域模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

ORDER_STATUS_LABELS = {
    0: "待支付",
    10: "已支付",
    20: "待发货",
    30: "已发货",
    40: "已完成",
    50: "已取消",
    60: "退款中",
    70: "已退款",
}
PAY_STATUS_LABELS = {0: "未支付", 1: "已支付", 2: "部分退款", 3: "全额退款"}
SOURCE_LABELS = {1: "APP", 2: "小程序", 3: "H5"}


class OrderRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    order_no: str
    user_id: int
    order_status: int
    pay_status: int
    source: int
    total_amount: float
    discount_amount: float
    freight_amount: float
    payable_amount: float
    paid_amount: float = 0
    refund_amount: float = 0
    coupon_id: int | None = None
    remark: str = ""
    expire_time: str | None = None
    pay_time: str | None = None
    finish_time: str | None = None
    cancel_time: str | None = None
    created_at: str
    updated_at: str
    user: dict | None = None
    items: list[dict] = Field(default_factory=list)
    address: dict | None = None
    payments: list[dict] = Field(default_factory=list)
    refunds: list[dict] = Field(default_factory=list)
    status_logs: list[dict] = Field(default_factory=list)

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
