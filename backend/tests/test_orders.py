"""订单存储用例：读取、按条件检索、大小写不敏感。"""

from __future__ import annotations

from backend.infrastructure.config import settings
from backend.infrastructure.persistence.order_store import JsonOrderStore


def _store() -> JsonOrderStore:
    return JsonOrderStore(settings.orders_file)


def test_loads_fifty_orders() -> None:
    assert _store().count() == 50


def test_get_order_is_case_insensitive() -> None:
    store = _store()
    first = store.search(limit=1)[0]
    assert store.get(first.order_no.lower()) is not None
    assert store.get("SO197001019999") is None


def test_search_by_status_and_user() -> None:
    store = _store()
    refunding = store.search(status=60, limit=10)
    assert refunding and all(order.order_status == 60 for order in refunding)

    user_id = store.search(limit=1)[0].user_id
    by_user = store.search(user_id=user_id, limit=50)
    assert by_user and all(order.user_id == user_id for order in by_user)


def test_search_by_keyword_matches_order_no_or_product() -> None:
    store = _store()
    first = store.search(limit=1)[0]
    by_no = store.search(q=first.order_no[-6:], limit=10)
    assert any(order.order_no == first.order_no for order in by_no)

    product = first.items[0].product_name[:4]
    assert store.search(q=product, limit=50)


def test_search_respects_limit_and_sorts_desc() -> None:
    store = _store()
    results = store.search(limit=5)
    assert len(results) == 5
    created = [order.created_at for order in results]
    assert created == sorted(created, reverse=True)
