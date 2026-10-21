import { useCallback, useMemo, useState } from "react";
import { SearchOutlined } from "@ant-design/icons";
import { Button, Empty, Input, Spin, Tag, Timeline, Typography } from "antd";

import { listOrders } from "../api/agent";
import SiteSidebar from "../components/SiteSidebar";
import type { AgentInfo, OrderRecord } from "../types";

const { Text } = Typography;

function money(value: number): string {
  return `¥${value.toFixed(2)}`;
}

/** 电商订单查询页：条件检索 + 订单详情（明细/金额/支付/退款/状态时间线）。 */
export default function OrdersPage({ info }: { info: AgentInfo | null }) {
  const [orderNo, setOrderNo] = useState("");
  const [userId, setUserId] = useState("");
  const [validation, setValidation] = useState("");
  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedNo, setSelectedNo] = useState<string | null>(null);

  const search = useCallback(async () => {
    if (!orderNo.trim() && !userId.trim()) {
      setValidation("请输入订单号或 user_id");
      setOrders([]);
      return;
    }
    if (userId.trim() && !/^\d+$/.test(userId.trim())) {
      setValidation("user_id 必须是数字");
      setOrders([]);
      return;
    }
    setValidation("");
    setLoading(true);
    setSelectedNo(null);
    try {
      setOrders(
        await listOrders({
          order_no: orderNo.trim() || undefined,
          user_id: userId.trim() ? Number(userId.trim()) : undefined,
          limit: 50,
        }),
      );
    } catch {
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, [orderNo, userId]);

  const selected = useMemo(
    () => orders.find((order) => order.order_no === selectedNo) ?? null,
    [orders, selectedNo],
  );

  return (
    <div className="shell">
      <SiteSidebar active="orders" info={info} />
      <main className="admin-main">
        <header className="topbar">
          <span className="topbar-title">订单查询</span>
          <span className="pill">共 {orders.length} 单</span>
          <span className="spacer" />
          <span className="pill">演示数据 · 50 单</span>
        </header>

        <div className="order-layout">
          <section className="order-list">
            <div className="filter-bar">
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="订单号 SO..."
                value={orderNo}
                onChange={(event) => setOrderNo(event.target.value.toUpperCase())}
                onPressEnter={() => void search()}
              />
              <Input
                allowClear
                placeholder="user_id，例如 10018"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                onPressEnter={() => void search()}
              />
              <Button type="primary" onClick={() => void search()} loading={loading}>
                查询
              </Button>
            </div>

            <div className="order-cards">
              {loading && orders.length === 0 ? (
                <Spin />
              ) : orders.length === 0 ? (
                <Empty description={validation || "没有匹配的订单"} />
              ) : (
                orders.map((order) => (
                  <button
                    type="button"
                    key={order.order_no}
                    className={order.order_no === selectedNo ? "order-card active" : "order-card"}
                    onClick={() => setSelectedNo(order.order_no)}
                  >
                    <div className="order-card-head">
                      <span className="mono">{order.order_no}</span>
                      <span className={`tag tag-status-${order.status_label}`}>{order.status_label}</span>
                      <span className="spacer" />
                      <span className="ok-text">{money(order.payable_amount)}</span>
                    </div>
                    <div className="order-card-body">
                      {order.items.map((item) => item.product_name).join(" / ")}
                    </div>
                    <div className="ticket-meta">
                      <span>{order.user?.name ?? `用户 ${order.user_id}`}</span>
                      <span>{order.items.length} 件商品</span>
                      <span>{order.created_at}</span>
                      <span>{order.source_label}</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <aside className="side-panel order-detail">
            {!selected ? (
              <div className="detail-empty">
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择左侧订单查看详情" />
              </div>
            ) : (
              <>
                <div className="panel-head">
                  <span className="panel-title">{selected.order_no}</span>
                  <span className={`tag tag-status-${selected.status_label}`}>{selected.status_label}</span>
                  <span className="spacer" />
                  <Tag variant="filled">{selected.pay_status_label}</Tag>
                </div>
                <div className="detail-scroll">
                  <div className="detail-block">
                    <Text type="secondary">收货信息</Text>
                    <div>
                      {selected.address?.receiver_name} {selected.address?.receiver_phone}
                    </div>
                    <div className="muted">
                      {selected.address?.province} {selected.address?.city} {selected.address?.district}{" "}
                      {selected.address?.detail_address}
                    </div>
                  </div>

                  <div className="detail-block">
                    <Text type="secondary">商品明细</Text>
                    {selected.items.map((item) => (
                      <div className="detail-item" key={`${item.product_name}-${item.sku_spec}`}>
                        <div>
                          <div>{item.product_name}</div>
                          <div className="muted">{item.sku_spec}</div>
                        </div>
                        <div className="mono">
                          {money(item.price)} × {item.quantity}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="detail-block amounts">
                    <div><span>商品总额</span><span className="mono">{money(selected.total_amount)}</span></div>
                    <div><span>优惠</span><span className="mono">-{money(selected.discount_amount)}</span></div>
                    <div><span>运费</span><span className="mono">{money(selected.freight_amount)}</span></div>
                    <div className="amount-total"><span>应付</span><span className="mono">{money(selected.payable_amount)}</span></div>
                    <div><span>实付</span><span className="mono">{money(selected.paid_amount)}</span></div>
                    {selected.refund_amount > 0 && (
                      <div><span>已退款</span><span className="mono">{money(selected.refund_amount)}</span></div>
                    )}
                  </div>

                  {selected.payments.length > 0 && (
                    <div className="detail-block">
                      <Text type="secondary">支付单</Text>
                      {selected.payments.map((payment) => (
                        <div className="muted" key={payment.payment_no}>
                          {payment.payment_no} · {payment.channel_name} · {money(payment.amount)} · {payment.paid_at}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="detail-block">
                    <Text type="secondary">状态时间线</Text>
                    <Timeline
                      style={{ marginTop: 10 }}
                      items={selected.status_logs.map((log) => ({
                        children: (
                          <div>
                            <div>{log.remark}</div>
                            <div className="timeline-meta">{log.created_at}</div>
                          </div>
                        ),
                      }))}
                    />
                  </div>
                </div>
              </>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}
