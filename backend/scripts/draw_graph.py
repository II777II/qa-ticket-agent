"""把当前 LangGraph 编排渲染成图（画的是运行时真实结构，不是手绘的示意图）。

三种输出，按需组合：

    python -m backend.scripts.draw_graph                # 终端 ASCII 图 + 导出 docs/graph.mmd
    python -m backend.scripts.draw_graph --png          # 再渲染 docs/graph.png
    python -m backend.scripts.draw_graph --html         # 再导出 docs/graph.html（离线可看，用本地 mermaid）

在 Jupyter / IPython 里内嵌显示（你要的 Python.display 方式）：

    from IPython.display import Image, display
    from backend.runtime import create_runtime

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
import sys
from pathlib import Path

from backend.config import PROJECT_ROOT
from backend.runtime import create_runtime

DOCS_DIR = PROJECT_ROOT / "docs"


def _display_in_jupyter(png: bytes) -> None:
    """在 IPython/Jupyter 里直接把图显示出来；命令行环境自动跳过。"""
    try:
        from IPython.display import Image, display  # type: ignore[import-not-found]
    except ImportError:
        print("提示：当前环境没有 IPython，PNG 已存盘；在 Jupyter 里可用 "
              "`display(Image(png_bytes))` 内嵌显示。")
        return
    display(Image(png))


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 LangGraph 结构图")
    parser.add_argument("--out-dir", default=str(DOCS_DIR), help="输出目录（默认 docs/）")
    parser.add_argument("--ascii", action="store_true", help="只打印终端 ASCII 图")
    parser.add_argument("--png", action="store_true", help="额外渲染 PNG（默认走 mermaid.ink，需要联网）")
    parser.add_argument("--html", action="store_true", help="额外导出可离线打开的 HTML（按需从 CDN 加载 mermaid）")
    parser.add_argument("--both-variants", action="store_true", help="同时画「最小图（无工具/无检索）」作对照")
    args = parser.parse_args()

    runtime = create_runtime()
    drawable = runtime.graph.get_graph()
    out_dir = Path(args.out_dir)

    print("=== 运行时真实结构（终端 ASCII）===")
    try:
        print(drawable.draw_ascii())
    except ImportError:
        print("（缺少 grandalf，跳过 ASCII：pip install grandalf）")

    if args.ascii:
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    mermaid = drawable.draw_mermaid()
    mmd_path = out_dir / "graph.mmd"
    mmd_path.write_text(mermaid, encoding="utf-8")
    print(f"=== Mermaid 源已写出：{mmd_path} ===")
    print(mermaid)

    if args.both_variants:
        from backend.graph import build_graph

        minimal = build_graph(llm=runtime.llm).get_graph()  # 不带工具与检索的最小图
        minimal_path = out_dir / "graph-minimal.mmd"
        minimal_path.write_text(minimal.draw_mermaid(), encoding="utf-8")
        print(f"=== 最小图（无工具/无检索）已写出：{minimal_path} ===")
        try:
            print(minimal.draw_ascii())
        except ImportError:
            pass

    if args.html:
        html_path = out_dir / "graph.html"
        html_path.write_text(_mermaid_html(mermaid), encoding="utf-8")
        print(f"=== HTML 已写出（浏览器打开即可，需能访问 CDN）：{html_path} ===")

    if args.png:
        png_path = out_dir / "graph.png"
        try:
            png = drawable.draw_mermaid_png(output_file_path=str(png_path))
        except Exception as exc:  # 联网失败 / 渲染服务不可用都不该让脚本炸掉
            print(f"PNG 渲染失败：{type(exc).__name__}: {exc}")
            print("可选替代：① 打开 docs/graph.mmd 粘到支持 Mermaid 的编辑器；"
                  "② 装 pyppeteer 后把 draw_method 换成 MermaidDrawMethod.PYPPETEER。")
        else:
            print(f"=== PNG 已写出：{png_path}（{len(png)} 字节）===")
            _display_in_jupyter(png)

    return 0


def _mermaid_html(mermaid: str) -> str:
    """把 Mermaid 文本包成可离线打开的单页（图形渲染按需从 CDN 取 mermaid）。"""
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
