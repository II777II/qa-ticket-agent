import { Button, Empty, Tag, Typography } from "antd";

import { navigate } from "../router";
import type { OrderSummary } from "../types";

const { Text } = Typography;

export interface OrderPanelProps {
  orders: OrderSummary[];
  question: string;
}

/** 对话右侧的订单查询结果：跟随当前这一轮 read 分支的 order_query 工具结果。 */
export default function OrderPanel({ orders, question }: OrderPanelProps) {
  return (
    <aside className="side-panel">
      <div className="panel-head">
        <span className="panel-title">订单查询结果</span>
        <Tag variant="filled">本轮 {orders.length} 笔</Tag>
        <span className="spacer" />
        <Button size="small" type="text" onClick={() => navigate("/orders")}>
          订单页 ↗
        </Button>
      </div>

      <div className="panel-query">
        <Text type="secondary">本轮问题</Text>
        <div className="query-text">{question || "（这一轮还没有提问）"}</div>
      </div>

      {orders.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本轮没有查询到订单" />
      ) : (
        <div className="ticket-list">
          {orders.map((order) => (
            <article className="order-mini-card" key={order.order_no}>
              <div className="order-card-head">
                <span className="mono">{order.order_no}</span>
                <span className={`tag tag-status-${order.status}`}>{order.status}</span>
                <span className="spacer" />
                <span className="ok-text">¥{order.payable_amount.toFixed(2)}</span>
              </div>
              <div className="ticket-title">{order.items.map((item) => item.name).join(" / ")}</div>
              <div className="ticket-meta">
                <span>{order.customer}</span>
                <span>{order.items.length} 件商品</span>
                <span>{order.created_at}</span>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="panel-foot">
        <Text type="secondary" style={{ fontSize: 11 }}>
          数据来自 read 分支的确定性 order_query 工具；完整明细可在订单查询页查看。
        </Text>
      </div>
    </aside>
  );
}
