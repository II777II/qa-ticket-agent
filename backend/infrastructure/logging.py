"""日志初始化（属于基础设施：怎么输出是外部设施问题，业务层只管拿 logger）。

刻意用手写 Handler + Formatter，而不是 `logging.basicConfig`：
basicConfig 判的是 **root** 有没有 handler，一旦 uvicorn / pytest 先配过 root，
它就会静默失效，日志凭空消失。这里改成「看自己要挂的那个 logger」再决定装不装。
"""

from __future__ import annotations

import logging
import sys

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """给 root logger 装一个 handler；已经配过就沿用别人的配置。"""
    root = logging.getLogger()
    if root.handlers:  # 避免重复注册导致同一条日志打两遍
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
