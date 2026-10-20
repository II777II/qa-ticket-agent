"""把当前 LangGraph 编排渲染成图（画的是运行时真实结构，不是手绘的示意图）。

三种输出，按需组合：

    python -m backend.scripts.draw_graph                # 终端 ASCII 图 + 导出 docs/graph.mmd
    python -m backend.scripts.draw_graph --png          # 再渲染 docs/graph.png
    python -m backend.scripts.draw_graph --html         # 再导出 docs/graph.html（离线可看，用本地 mermaid）

在 Jupyter / IPython 里内嵌显示（你要的 Python.display 方式）：

    from IPython.display import Image, display
    from backend.application.runtime import create_runtime

    graph = create_runtime().graph
    display(Image(graph.get_graph().draw_mermaid_png()))        # 需要联网渲染
    # 离线时用 ASCII 更省事：
    print(graph.get_graph().draw_ascii())

图片是怎么来的：LangGraph 先把图转成 Mermaid 文本，再交给渲染器出图。
默认渲染走 mermaid.ink（需要联网）；内网环境可以改成 draw_method=MermaidDrawMethod.PYPPETEER
（需要 `pip install pyppeteer` 并首次下载 Chromium），或者直接把 docs/graph.mmd 粘到支持
Mermaid 的编辑器 / 在线预览里看。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from backend.application.runtime import create_runtime
from backend.infrastructure.config import PROJECT_ROOT

DOCS_DIR = PROJECT_ROOT / "docs"

# 本地渲染用：优先用仓库里已有的 mermaid（@ant-design/x 的依赖），再用本机浏览器截图
LOCAL_MERMAID_CANDIDATES = [
    PROJECT_ROOT / "frontend" / "node_modules" / "mermaid" / "dist" / "mermaid.min.js",
]
BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _prepare_local_mermaid(out_dir: Path) -> Path | None:
    """把本地 mermaid.min.js 复制到 docs/vendor/，让 HTML 不依赖 CDN。"""
    source = next((path for path in LOCAL_MERMAID_CANDIDATES if path.is_file()), None)
    if source is None:
        return None
    vendor_dir = out_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    target = vendor_dir / "mermaid.min.js"
    shutil.copyfile(source, target)
    return target


def _render_png_with_browser(out_dir: Path, mermaid: str, png_path: Path, size: tuple[int, int] = (1400, 1200)) -> str:
    """用本机 Chrome/Edge 无头截图，完全不联网。返回结果说明。

    截的是「只有一个图、没有别的内容」的临时页面，截完再裁掉空白边框——
    直接把公开的 graph.html 截图的话，标题和 Mermaid 源文本会一起进图片。
    """
    browser = next((path for path in BROWSER_CANDIDATES if Path(path).is_file()), None)
    if browser is None:
        return "找不到本机 Chrome/Edge，无法本地渲染"

    render_page = out_dir / ".graph-render.html"
    render_page.write_text(_mermaid_html(mermaid, True, diagram_only=True), encoding="utf-8")
    for path in (png_path,):
        if path.exists():
            path.unlink()

    command = [
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
        f"--window-size={size[0]},{size[1]}", "--virtual-time-budget=8000",
        f"--screenshot={png_path}", render_page.as_uri(),
    ]
    try:
        subprocess.run(command, check=False, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"本地渲染失败：{type(exc).__name__}: {exc}"
    finally:
        render_page.unlink(missing_ok=True)

    if not png_path.exists():
        return "本地渲染未产出文件"
    note = _crop_whitespace(png_path)
    return f"本地渲染成功（{browser.split(chr(92))[-1]}，{note}）"


def _crop_whitespace(png_path: Path, padding: int = 16) -> str:
    """裁掉截图四周的空白（没装 Pillow 就原样保留）。"""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return "未装 Pillow，未裁剪"
    with Image.open(png_path) as image:
        rgb = image.convert("RGB")
        background = Image.new("RGB", rgb.size, (255, 255, 255))
        box = ImageChops.difference(rgb, background).getbbox()
        if box is None:
            return "整图空白，未裁剪"
        left, top, right, bottom = box
        cropped = rgb.crop(
            (max(left - padding, 0), max(top - padding, 0), min(right + padding, rgb.width), min(bottom + padding, rgb.height))
        )
        cropped.save(png_path)
    return f"已裁成 {cropped.size[0]}×{cropped.size[1]}"


def _render_png_with_api(mermaid: str, png_path: Path) -> bytes | None:
    """把「标注后的」Mermaid 文本交给 mermaid.ink 渲染。

    注意：不能直接用 `graph.draw_mermaid_png()`——那是拿 LangGraph 自己生成的
    未标注文本去渲染，节点上就没有工具名与 RAG 步骤了。这里用 LangChain 的
    底层渲染函数，参数就是 Mermaid 文本本身（私有函数，换版本时注意兼容）。
    """
    try:
        from langchain_core.runnables.graph_mermaid import _render_mermaid_using_api
    except ImportError:
        return None
    try:
        return _render_mermaid_using_api(
            mermaid,
            output_file_path=str(png_path),
            max_retries=2,
            retry_delay=2.0,
        )
    except Exception as exc:
        print(f"mermaid.ink 渲染失败（{type(exc).__name__}），改用本机浏览器离线渲染")
        return None


def _display_in_jupyter(png: bytes) -> None:
    """在 IPython/Jupyter 里直接把图显示出来；命令行环境自动跳过。"""
    try:
        from IPython.display import Image, display  # type: ignore[import-not-found]
    except ImportError:
        print("提示：当前环境没有 IPython，PNG 已存盘；在 Jupyter 里可用 "
              "`display(Image(png_bytes))` 内嵌显示。")
        return
    display(Image(png))


def _annotate(mermaid: str, *, tool_names: list[str], has_retriever: bool) -> str:
    """给节点与边补上能自解释的标注。

    图里只写 agent / tools 等于什么都没说：agent 内部做不做 RAG、走哪几步，
    tools 里装了哪些工具，条件边按什么判断——这些全部从运行时读出来标上去，
    这样图和代码不会各说各话。
    """
    # tools 节点：写出真实注册的工具名
    if tool_names:
        tools_label = "tools<br/>" + " / ".join(tool_names)
        mermaid = re.sub(r"(?m)^(\s*)tools\(tools\)\s*$", rf'\1tools["{tools_label}"]', mermaid)

    # agent 节点：写出内部步骤（含 RAG）
    steps = ["agent"]
    steps.append("检索知识库 (RAG)" if has_retriever else "未接入检索")
    steps.extend(["命中片段拼进系统提示", "llm.bind_tools().invoke()"])
    agent_label = "<br/>".join(steps)
    mermaid = re.sub(r"(?m)^(\s*)agent\(agent\)\s*$", rf'\1agent["{agent_label}"]', mermaid)

    # 条件边：LangGraph 不标判断条件，这里补上
    mermaid = re.sub(r"(?m)^(\s*)agent\s*-\.->\s*__end__;", r"\1agent -.->|无 tool_calls| __end__;", mermaid)
    mermaid = re.sub(r"(?m)^(\s*)agent\s*-\.->\s*tools;", r"\1agent -.->|有 tool_calls| tools;", mermaid)

    # 四路路由主干：给节点与条件边补上中文说明
    labels = {
        "preprocess": "preprocess<br/>清洗 / 截断",
        "classify": "classify<br/>LLM 意图识别 + 规则兜底",
        "knowledge": "knowledge<br/>RAG 问答",
        "query": "query<br/>订单查询",
        "service": "service<br/>工单草稿",
        "fallback": "fallback<br/>投诉 / 闲聊 / 转人工",
    }
    for node, label in labels.items():
        mermaid = re.sub(rf"(?m)^(\s*){node}\({node}\)\s*$", rf'\1{node}["{label}"]', mermaid)
    for branch in ("knowledge", "query", "service", "fallback"):
        mermaid = re.sub(
            rf"(?m)^(\s*)classify\s*-\.->\s*{branch};",
            rf"\1classify -.->|{branch}| {branch};",
            mermaid,
        )
    return mermaid


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 LangGraph 结构图")
    parser.add_argument("--out-dir", default=str(DOCS_DIR), help="输出目录（默认 docs/）")
    parser.add_argument("--ascii", action="store_true", help="只打印终端 ASCII 图")
    parser.add_argument("--png", action="store_true", help="额外渲染 PNG（默认走 mermaid.ink，需要联网）")
    parser.add_argument("--html", action="store_true", help="额外导出可离线打开的 HTML（用仓库里自带的 mermaid）")
    parser.add_argument("--local", action="store_true", help="PNG 跳过 mermaid.ink，直接用本机浏览器离线渲染")
    args = parser.parse_args()

    runtime = create_runtime()
    drawable = runtime.graph.get_graph()
    out_dir = Path(args.out_dir)
    tool_names = [getattr(tool, "name", str(tool)) for tool in runtime.tools]
    has_retriever = runtime.retriever is not None

    print("=== 运行时真实结构（终端 ASCII）===")
    try:
        print(drawable.draw_ascii())
    except ImportError:
        print("（缺少 grandalf，跳过 ASCII：pip install grandalf）")
    print(f"图内节点：{' / '.join(sorted(drawable.nodes))}")
    print(f"运行时暴露的工具：{'、'.join(tool_names) if tool_names else '无'}")

    if args.ascii:
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    mermaid = _annotate(drawable.draw_mermaid(), tool_names=tool_names, has_retriever=has_retriever)
    mmd_path = out_dir / "graph.mmd"
    mmd_path.write_text(mermaid, encoding="utf-8")
    print(f"=== Mermaid 源已写出：{mmd_path} ===")
    print(mermaid)

    html_path: Path | None = None
    if args.html or args.png:
        html_path = out_dir / "graph.html"
        vendor = _prepare_local_mermaid(out_dir)
        html_path.write_text(_mermaid_html(mermaid, vendor is not None), encoding="utf-8")
        source = "本地 mermaid（离线可用）" if vendor else "CDN（打开时需联网）"
        print(f"=== HTML 已写出：{html_path}（{source}）===")

    if args.png:
        png_path = out_dir / "graph.png"
        png: bytes | None = None

        if not args.local:
            png = _render_png_with_api(mermaid, png_path)
            if png is not None:
                print(f"=== PNG 已写出（mermaid.ink 渲染）：{png_path}（{len(png)} 字节）===")

        if png is None and html_path is not None:
            result = _render_png_with_browser(out_dir, mermaid, png_path)
            print(f"=== {result} ===")
            if png_path.exists():
                png = png_path.read_bytes()

        if png is None:
            print(
                "PNG 没渲染出来。替代方案：① 直接看 docs/graph.html；"
                "② 把 docs/graph.mmd 粘到支持 Mermaid 的编辑器；"
                "③ 装 pyppeteer 后改用 MermaidDrawMethod.PYPPETEER。"
            )
        else:
            _display_in_jupyter(png)

    return 0


_HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>问答工单 Agent · LangGraph 结构图</title>
    <style>
      body {{ font-family: system-ui, "Microsoft YaHei", sans-serif; margin: {margin}; }}
{extra_css}    </style>
  </head>
  <body>
{body_head}    <pre class="mermaid">{mermaid}</pre>
{body_tail}{script}
  </body>
</html>
"""

_BODY_HEAD_FULL = """    <h1>问答工单 Agent · LangGraph 结构图</h1>
    <p>由 <code>python -m backend.scripts.draw_graph --html</code> 从运行时图导出。</p>
"""

_BODY_TAIL_FULL = """    <h2>Mermaid 源文本</h2>
    <pre>{escaped}</pre>
"""

_BODY_TAIL_PLAIN = ""

# 截图专用：让背景全白、不要内边距，否则裁剪会按整行宽度算
_CSS_DIAGRAM_ONLY = "      pre.mermaid { background: transparent; padding: 0; margin: 0; }\n"
_CSS_FULL = "      pre { background: #f6f8fa; padding: 16px; border-radius: 8px; overflow: auto; }\n"

_SCRIPT_LOCAL = """    <script src="vendor/mermaid.min.js"></script>
    <script>
      mermaid.initialize({{ startOnLoad: false, theme: "neutral" }});
      mermaid.run({{ querySelector: ".mermaid" }});
    </script>"""

_SCRIPT_CDN = """    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});
    </script>"""


def _mermaid_html(mermaid: str, use_local_mermaid: bool, diagram_only: bool = False) -> str:
    """把 Mermaid 文本包成单页；仓库里有 mermaid 就完全离线，否则退回 CDN。

    diagram_only=True 时只输出图本身（给无头浏览器截图用），不带标题与源文本。
    """
    return _HTML_TEMPLATE.format(
        mermaid=mermaid,
        escaped=mermaid.replace("&", "&amp;").replace("<", "&lt;"),
        script=_SCRIPT_LOCAL if use_local_mermaid else _SCRIPT_CDN,
        margin="0" if diagram_only else "32px",
        extra_css=_CSS_DIAGRAM_ONLY if diagram_only else _CSS_FULL,
        body_head="" if diagram_only else _BODY_HEAD_FULL,
        body_tail=_BODY_TAIL_PLAIN if diagram_only else _BODY_TAIL_FULL.format(
            escaped=mermaid.replace("&", "&amp;").replace("<", "&lt;")
        ),
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>问答工单 Agent · LangGraph 结构图</title>
    <style>
      body {{ font-family: system-ui, "Microsoft YaHei", sans-serif; margin: 32px; }}
      pre {{ background: #f6f8fa; padding: 16px; border-radius: 8px; overflow: auto; }}
    </style>
  </head>
  <body>
    <h1>问答工单 Agent · LangGraph 结构图</h1>
    <p>由 <code>python -m backend.scripts.draw_graph --html</code> 从运行时图导出。</p>
    <pre class="mermaid">{mermaid}</pre>
    <h2>Mermaid 源文本</h2>
    <pre>{mermaid.replace("&", "&amp;").replace("<", "&lt;")}</pre>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
