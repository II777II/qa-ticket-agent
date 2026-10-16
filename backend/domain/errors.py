"""领域异常。

用专门类型替掉散落的 ValueError：上层据此决定是回 400、记日志还是让模型自纠，
而不是靠匹配错误字符串。
"""

from __future__ import annotations


class DomainError(Exception):
    """领域层异常基类。"""


class UnknownStatusError(DomainError):
    """工单状态不在允许取值内。"""


class TicketNotFoundError(DomainError):
    """按单号找不到工单。"""
