"""订单存储用例：仅按订单号或 user_id 查询。"""

from __future__ import annotations

from backend.infrastructure.core import JsonOrderStore, settings


def _store() -> JsonOrderStore:
    return JsonOrderStore(settings.orders_file)


def test_loads_fifty_orders() -> None:
    assert _store().count() == 50


def test_get_order_is_case_insensitive() -> None:
    store = _store()
    assert store.get("so202609160001") is not None
    assert store.get("SO197001019999") is None


def test_search_by_user_id_only() -> None:
    store = _store()
    by_user = store.search(user_id=10002, limit=50)
    assert by_user and all(order.user_id == 10002 for order in by_user)
    assert store.search() == []


def test_exact_order_lookup() -> None:
    store = _store()
    assert store.get("SO202609160001") is not None
    assert store.get("SO20260916000") is None


def test_user_search_respects_limit_and_sorts_desc() -> None:
    store = _store()
    results = store.search(user_id=10002, limit=2)
    assert len(results) == 2
    created = [order.created_at for order in results]
    assert created == sorted(created, reverse=True)
