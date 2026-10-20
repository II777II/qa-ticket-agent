"""电商订单领域模型（与 Postgres 表形状一一对应）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field

ORDER_STATUS_LABELS = {
    0: "待支付", 10: "已支付", 20: "待发货", 30: "已发货",
    40: "已完成", 50: "已取消", 60: "退款中", 70: "已退款",
}
PAY_STATUS_LABELS = {0: "未支付", 1: "已支付", 2: "部分退款", 3: "全额退款"}
SOURCE_LABELS = {1: "APP", 2: "小程序", 3: "H5"}


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    # 聚合视图里的明细没有 id/order_id（分表数据才有），所以允许为空
    id: int | None = None
    order_id: int | None = None
    order_no: str | None = None
    sku_id: int
    product_id: int
    product_name: str
    sku_spec: str | None = None
    product_img: str | None = None
    price: float
    quantity: int
    item_amount: float
    discount_amount: float = 0.0
    payable_amount: float
    refund_status: int = 0


class OrderAddress(BaseModel):
    model_config = ConfigDict(extra="allow")

    receiver_name: str
    receiver_phone: str
    province: str
    city: str
    district: str
    detail_address: str
    postal_code: str | None = None


class OrderPayment(BaseModel):
    model_config = ConfigDict(extra="allow")

    payment_no: str
    channel: int
    channel_name: str | None = None
    out_trade_no: str | None = None
    amount: float
    status: int
    paid_at: str | None = None


class OrderRefund(BaseModel):
    model_config = ConfigDict(extra="allow")

    refund_no: str
    amount: float
    reason: str | None = None
    status: int
    refunded_at: str | None = None


class OrderStatusLog(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_status: int
    to_status: int
    operator_type: int
    remark: str = ""
    created_at: str


class OrderRecord(BaseModel):
    """订单聚合（orders.json 的一条）。"""

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
    paid_amount: float = 0.0
    refund_amount: float = 0.0
    coupon_id: int | None = None
    remark: str = ""
    expire_time: str | None = None
    pay_time: str | None = None
    finish_time: str | None = None
    cancel_time: str | None = None
    created_at: str
    updated_at: str
    user: dict | None = None
    items: list[OrderItem] = []
    address: OrderAddress | None = None
    payments: list[OrderPayment] = []
    refunds: list[OrderRefund] = []
    status_logs: list[OrderStatusLog] = []

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
