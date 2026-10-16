"""命令行验收脚本。

阶段一的验收标准就是「命令行能流式输出模型回答」，所以这个脚本本身就是交付物之一：
它绕开 HTTP，直接跑 LangGraph，用来判断问题出在模型/编排侧还是接口/前端侧。

用法（项目根目录下）：
    python -m backend.scripts.cli_chat                    # 交互式多轮
    python -m backend.scripts.cli_chat --once "怎么重设密码"  # 单轮，方便脚本化自检
    python -m backend.scripts.cli_chat --thread demo-1
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from backend.infrastructure.config import settings
from backend.runtime import AgentRuntime, create_runtime
from backend.schemas import (
    EVENT_CITATION,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_START,
    EVENT_TICKET,
    EVENT_TOKEN,
    EVENT_TOOL,
)


def _ensure_utf8_stdio() -> None:
    """输出被重定向到管道/文件时，Windows 默认按 GBK 写中文，容易变乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")


async def run_once(
    runtime: AgentRuntime,
    message: str,
    thread_id: str,
    show_prefix: bool = True,
) -> None:
    if show_prefix:
        print("\n助理 > ", end="", flush=True)

    async for event, payload in runtime.stream(message, thread_id):
        if event == EVENT_START:
            tag = "演示模式" if payload["mock"] else payload["provider"]
            print(f"[{tag}] ", end="", flush=True)
        elif event == EVENT_TOKEN:
            print(payload["text"], end="", flush=True)
        elif event == EVENT_TOOL:
            if payload.get("phase") == "call":
                print(f"\n  <调用工具> {payload.get('name')}", flush=True)
            else:
                flag = "ok" if payload.get("ok") else "失败"
                print(f"  <工具返回> {payload.get('name')} [{flag}] {payload.get('message', '')}", flush=True)
        elif event == EVENT_TICKET:
            for ticket in payload.get("tickets", []):
                print(
                    f"  <工单> {ticket['id']} [{ticket['status']}] {ticket['title']}"
                    f"（{ticket['category']}/{ticket['priority']}）",
                    flush=True,
                )
        elif event == EVENT_CITATION:
            print(
                f"  <引用 [{payload.get('index')}]> {payload.get('source')} · {payload.get('title')}"
                f"（score={payload.get('score')}）",
                flush=True,
            )
        elif event == EVENT_ERROR:
            print(f"\n[错误] {payload['type']}: {payload['message']}", file=sys.stderr, flush=True)
        elif event == EVENT_DONE:
            print()


async def main() -> int:
    parser = argparse.ArgumentParser(description="问答工单 Agent 命令行验收")
    parser.add_argument("--once", metavar="QUESTION", help="只跑一轮就退出")
    parser.add_argument("--thread", default="cli", help="会话 ID（短期记忆按它隔离）")
    parser.add_argument("--tickets", action="store_true", help="打印当前工单列表后退出")
    args = parser.parse_args()

    runtime = create_runtime()
    info = runtime.describe()
    print(
        f"provider={info['provider']}  model={info['model'] or '(内置)'}  "
        f"tools={len(info['tools'])}  memory={info['checkpointer'] or '未接入'}  "
        f"tickets={info['tickets']}  "
        f"thread={args.thread}"
    )

    if args.tickets:
        store = runtime.store
        records = store.list(limit=None) if store else []
        if not records:
            print("（还没有工单）")
        for record in records:
            print(
                f"{record.id}  [{record.status}] {record.category}/{record.priority}  "
                f"{record.title}  （{record.contact}，{record.created_at}）"
            )
        return 0

    if args.once:
        await run_once(runtime, args.once, args.thread, show_prefix=False)
        return 0

    print("输入问题回车发送；exit / quit / :q 退出。")
    while True:
        try:
            line = (await asyncio.to_thread(input, "\n你 > ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in {"exit", "quit", ":q"}:
            return 0
        await run_once(runtime, line, args.thread)


if __name__ == "__main__":
    _ensure_utf8_stdio()
    if settings.mock_mode:
        print("提示：当前是演示模式（LLM_PROVIDER=mock），回答是内置占位内容。")
    raise SystemExit(asyncio.run(main()))
