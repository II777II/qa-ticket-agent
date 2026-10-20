"""工具适配层：把「Agent 能做的事」包装成模型可调用的工具。

这一层只做三件事：
1. 声明参数 schema（Pydantic 的 Literal 会变成 JSON Schema 的 enum，模型编不出脏值）；
2. 把参数翻译成对 application/tickets/service.py 的调用（业务动作在那一层）；
3. 把返回值序列化成 JSON 字符串——模型读得懂，接口层也能解析出工单号。

报错策略：参数不合法时 StructuredTool 抛 ValidationError，LangGraph 的 ToolNode
默认会把异常转成 ToolMessage 回给模型，让模型自己纠正参数再试，而不是整轮失败。

新增工具不需要改 graph.py：build_graph 会按 tools 是否为空自动挂上 Tool 节点；
但「需要新增什么业务动作」应该先落到 tickets 服务上，这里只做适配。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool

from backend.application.orders import OrderService
from backend.application.tickets import TicketService
from backend.domain import TicketCreate
from backend.domain.orders import ORDER_STATUS_LABELS, OrderRecord


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


STATUS_BY_LABEL = {label: code for code, label in ORDER_STATUS_LABELS.items()}


def _order_summary(order: OrderRecord) -> dict[str, Any]:
    return {
        "order_no": order.order_no,
        "status": order.status_label,
        "pay_status": order.pay_status_label,
        "customer": (order.user or {}).get("name") or order.user_id,
        "payable_amount": order.payable_amount,
        "paid_amount": order.paid_amount,
        "refund_amount": order.refund_amount,
        "created_at": order.created_at,
        "items": [
            {"name": item.product_name, "spec": item.sku_spec, "quantity": item.quantity, "price": item.price}
            for item in order.items
        ],
    }


def create_tools(tickets: TicketService, orders: OrderService, *, include_tickets: bool = True) -> list[BaseTool]:
    """按工单用例创建工具集（依赖注入，避免全局单例）。"""

    @tool("create_ticket", args_schema=TicketCreate)
    def create_ticket(
        title: str,
        description: str,
        category: str,
        priority: str,
        contact: str,
    ) -> str:
        """当帮助中心无法解决订单/物流/售后问题、或用户明确要求时，创建一张售后工单。

        所有字段都要来自用户的真实描述：信息不全（尤其是订单号/联系人）时先追问，
        不要用「未知」「同上」这类占位内容凑数，也不要在用户只是咨询时建单。
        """
        record, duplicated = tickets.create(
            TicketCreate(
                title=title,
                description=description,
                category=category,
                priority=priority,
                contact=contact,
            )
        )
        return _dump(
            {
                "ok": True,
                "action": "create_ticket",
                "duplicated": duplicated,
                "message": "已存在相同标题的未关闭工单，未重复创建" if duplicated else "工单已创建",
                "ticket": record.model_dump(),
            }
        )

    @tool("query_ticket")
    def query_ticket(ticket_id: str = "", contact: str = "", urge: bool = False) -> str:
        """查询工单进度。

        有单号（形如 TK-20261016-0001）就按单号查；只说「我的工单」就按联系人查。
        用户要求催单时把 urge 置为 true，会在工单时间线上记一条催单记录。
        """
        if ticket_id:
            record = tickets.find(ticket_id)
            if record is None:
                return _dump(
                    {
                        "ok": False,
                        "action": "query_ticket",
                        "message": f"没有找到工单 {ticket_id}，请确认单号，或按联系人查询",
                    }
                )
            if urge:
                record = tickets.urge(record.id) or record
            return _dump({"ok": True, "action": "query_ticket", "tickets": [record.model_dump()]})

        if contact:
            records = tickets.list(contact=contact, limit=5)
            return _dump(
                {
                    "ok": True,
                    "action": "query_ticket",
                    "tickets": [r.model_dump() for r in records],
                    "message": "该联系人暂无工单" if not records else f"共 {len(records)} 张工单",
                }
            )

        return _dump(
            {
                "ok": False,
                "action": "query_ticket",
                "message": "需要提供工单号或联系人才能查询",
            }
        )

    @tool("escalate_to_human")
    def escalate_to_human(ticket_id: str, reason: str) -> str:
        """把工单转人工处理：用户明确要求转人工，或问题超出知识库与工具能力时使用。"""
        record = tickets.escalate(ticket_id, reason)
        if record is None:
            return _dump(
                {
                    "ok": False,
                    "action": "escalate_to_human",
                    "message": f"没有找到工单 {ticket_id}，请先确认单号；没有工单的话先建单再转人工",
                }
            )
        return _dump({"ok": True, "action": "escalate_to_human", "ticket": record.model_dump()})

    @tool("query_order")
    def query_order(order_no: str = "", keyword: str = "", status: str = "") -> str:
        """查询电商订单。

        用户给订单号（形如 SO202610210001）时按单号查；只给姓名/手机号/商品关键词时按关键词查；
        status 可传中文状态（待支付/已支付/待发货/已发货/已完成/已取消/退款中/已退款）。
        """
        status_code = None
        if status:
            status_code = STATUS_BY_LABEL.get(status.strip())
            if status_code is None:
                return _dump(
                    {
                        "ok": False,
                        "action": "query_order",
                        "message": f"未知订单状态 {status!r}，可选：{'、'.join(STATUS_BY_LABEL)}",
                    }
                )

        if order_no:
            order = orders.get(order_no)
            results = [order] if order is not None else []
        else:
            results = orders.search(q=keyword, status=status_code, limit=5)

        if not results:
            return _dump(
                {
                    "ok": False,
                    "action": "query_order",
                    "message": "没有找到匹配的订单，请提供订单号（SO 开头）或收货人姓名/手机号",
                }
            )
        return _dump(
            {
                "ok": True,
                "action": "query_order",
                "orders": [_order_summary(order) for order in results],
                "message": f"查到 {len(results)} 笔订单",
            }
        )

    # 当前产品只开放「订单查询」；工单工具保留在代码里供后续启用
    if include_tickets:
        return [create_ticket, query_ticket, escalate_to_human, query_order]
    return [query_order]
