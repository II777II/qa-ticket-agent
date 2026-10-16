"""持久化：工单存储实现 + 工厂。

上层的工单服务只依赖下面这几个方法（get / list / count / create / add_event），
换成 Postgres 时新写一个实现即可。
"""

from backend.infrastructure.persistence.factory import create_ticket_store
from backend.infrastructure.persistence.json_store import JsonTicketStore

__all__ = ["create_ticket_store", "JsonTicketStore"]
