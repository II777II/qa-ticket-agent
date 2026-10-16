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

from backend.application.tickets import TicketService
from backend.domain import TicketCreate


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def create_tools(tickets: TicketService) -> list[BaseTool]:
    """按工单用例创建工具集（依赖注入，避免全局单例）。"""

    @tool("create_ticket", args_schema=TicketCreate)
    def create_ticket(
        title: str,
        description: str,
        category: str,
        priority: str,
        contact: str,
    ) -> str:
        """当知识库无法解决用户问题、或用户明确要求时，创建一张 IT 服务台工单。

        所有字段都要来自用户的真实描述：信息不全（尤其是联系人）时先追问，不要用
        「未知」「同上」这类占位内容凑数，也不要在用户只是咨询时建单。
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

    return [create_ticket, query_ticket, escalate_to_human]
