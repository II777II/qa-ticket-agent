"""工单存储实现。

POC：JSON 文件（看得见、能直接改、零依赖）。
生产：Postgres 工单表——只要新实现保持下面这几个方法，工具层不用动。
"""

from backend.stores.json_store import JsonTicketStore

__all__ = ["JsonTicketStore"]
