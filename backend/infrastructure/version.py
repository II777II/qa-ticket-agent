"""版本信息：把当前 git 提交显示在界面上（修改前/后对得上号）。"""

from __future__ import annotations

import subprocess
from functools import lru_cache

from backend.infrastructure.config import PROJECT_ROOT


@lru_cache(maxsize=1)
def git_version() -> dict[str, str]:
    """返回 {sha, date}；没有 git（或容器里没装）时返回 unknown，不阻塞启动。"""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        ).stdout.strip()
        when = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d %H:%M"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {"sha": "unknown", "date": ""}
    return {"sha": sha or "unknown", "date": when}
