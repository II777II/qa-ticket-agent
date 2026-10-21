"""演示数据完整性：50 订单 / 50 篇 HTML，金额与引用关系自洽。"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

from backend.infrastructure.core import settings


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data


def test_orders_dataset_is_consistent() -> None:
    orders = json.loads(settings.orders_file.read_text(encoding="utf-8"))
    assert len(orders) == 50
    assert {order["order_status"] for order in orders} == {0, 10, 20, 30, 40, 50, 60, 70}

    for order in orders:
        assert round(order["total_amount"] - order["discount_amount"] + order["freight_amount"], 2) == order["payable_amount"]
        assert order["items"]
        assert order["address"]["receiver_name"]
        assert order["status_logs"]
        if order["order_status"] in (10, 20, 30, 40, 60, 70):
            assert order["payments"]
        if order["order_status"] in (60, 70):
            assert order["refunds"]
            assert order["refund_amount"] > 0


def test_kb_has_fifty_html_pages_matching_index() -> None:
    articles = json.loads(settings.kb_articles_file.read_text(encoding="utf-8"))
    assert len(articles) == 50
    pages = sorted(settings.kb_dir.glob("*.html"))
    assert len(pages) == 50

    for article in articles:
        page = settings.kb_dir / Path(article["path"]).name
        assert page.is_file(), f"缺少页面 {page}"
        text = page.read_text(encoding="utf-8")
        assert f'data-article-id="{article["article_no"]}"' in text
        parser = _TitleParser()
        parser.feed(text)
        assert article["title"] in parser.title


def test_kb_categories_and_tags() -> None:
    categories = json.loads((settings.kb_root / "categories.json").read_text(encoding="utf-8"))
    tags = json.loads((settings.kb_root / "tags.json").read_text(encoding="utf-8"))
    assert len(categories) == 8
    assert 10 <= len(tags) <= 30
