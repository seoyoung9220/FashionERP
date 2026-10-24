"""화면 새 주문 입력 (POST /api/sales) — CSV 업로드와 같은 검증 규칙, 1건만 추가."""
from datetime import date

import pytest

from app.database import connect, init_db
from app.errors import AppError
from app.importers.loader import seed_if_empty
from app.services.order_input import add_order
from app.services.trends import daily_sales
from app.utils import data_as_of


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()


def count(c, t):
    return c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]


def test_add_order_appends_one_row(conn):
    before = daily_sales(conn, "2026-10-24", "2026-10-24")["items"][0]
    r = add_order(conn, {"date": "2026-10-24", "product_id": "P001", "size": "M", "color": "Black"})
    o = r["order"]
    assert o["order_id"].startswith("P001-20261024-") and len(o["order_id"]) == len("P001-20261024-0001")
    assert o["product_name"] == "오버핏 울 코트" and o["category"] == "아우터" and o["qty"] == 1
    assert r["return_id"] is None and o["return_type_code"] is None   # 반품 아님 → null (0 아님)
    assert count(conn, "sales") == 2001 and count(conn, "returns") == 184
    after = daily_sales(conn, "2026-10-24", "2026-10-24")["items"][0]
    assert after["order_count"] == before["order_count"] + 1
    assert after["gross_sales"] == before["gross_sales"] + 189000      # 판매가(정가) 1장


@pytest.fixture
def today(monkeypatch):
    """'오늘'을 고정해 실행 날짜와 관계없이 같은 결과가 나오게 합니다."""
    monkeypatch.setattr("app.services.order_input.today_kst", lambda: date(2026, 10, 30))


def test_order_id_sequence_is_unique(conn, today):
    a = add_order(conn, {"date": "2026-10-25", "product_id": "P002", "size": "L", "color": "Blue"})
    b = add_order(conn, {"date": "2026-10-25", "product_id": "P002", "size": "L", "color": "Blue"})
    assert a["order"]["order_id"] == "P002-20261025-0001" and b["order"]["order_id"] == "P002-20261025-0002"
    assert data_as_of(conn) == date(2026, 10, 25)                        # 새 날짜가 기준일이 됨
    assert any("기준일" in w["message"] for w in a["warnings"])          # 기준일이 바뀌면 경고
    assert not any("기준일" in w["message"] for w in b["warnings"])      # 같은 날 두 번째는 바뀌지 않음


def test_future_date_is_rejected(conn, today):
    for day in ("2026-10-31", "2062-10-24"):                             # 내일 · 연도 오타
        with pytest.raises(AppError) as e:
            add_order(conn, {"date": day, "product_id": "P001", "size": "M", "color": "Black"})
        assert e.value.status == 400 and e.value.details[0]["column"] == "date"
    assert count(conn, "sales") == 2000 and data_as_of(conn) == date(2026, 10, 24)


def test_order_on_as_of_has_no_date_warning(conn, today):
    r = add_order(conn, {"date": "2026-10-24", "product_id": "P001", "size": "M", "color": "Black"})
    assert not any("기준일" in w["message"] for w in r["warnings"])


def test_return_order_creates_return_row(conn):
    r = add_order(conn, {"date": "2026-10-24", "product_id": "P007", "size": "L", "color": "Gray",
                         "is_returned": True, "return_type_code": "SIZE_FIT", "return_detail_text": "생각보다 작아요"})
    assert r["return_id"] == "R0185"
    row = conn.execute("SELECT return_type_code, return_detail_text FROM returns WHERE return_id='R0185'").fetchone()
    assert tuple(row) == ("SIZE_FIT", "생각보다 작아요")


def test_korean_label_is_saved_as_code(conn):
    r = add_order(conn, {"date": "2026-10-24", "product_id": "P007", "size": "L", "color": "Gray",
                         "is_returned": 1, "return_type_code": "사이즈/핏"})
    assert r["order"]["return_type_code"] == "SIZE_FIT"


BAD = [
    ({"date": "2026-10-24", "product_id": "P999", "size": "M", "color": "Black"}, "product_id"),
    ({"date": "2026/10/24", "product_id": "P001", "size": "M", "color": "Black"}, "date"),
    ({"date": "2026-10-24", "product_id": "P001", "size": "", "color": "Black"}, "size"),
    ({"date": "2026-10-24", "product_id": "P001", "size": "M", "color": "Black", "is_returned": True,
      "return_type_code": "WRONG"}, "return_type_code"),
]


def test_invalid_input_is_rejected_and_nothing_saved(conn):
    for body, column in BAD:
        with pytest.raises(AppError) as e:
            add_order(conn, body)
        assert e.value.status == 400 and any(d["column"] == column for d in e.value.details), column
    assert count(conn, "sales") == 2000


def test_return_without_type_is_saved_with_warning(conn):
    r = add_order(conn, {"date": "2026-10-24", "product_id": "P001", "size": "M", "color": "Black", "is_returned": True})
    assert r["order"]["return_type_code"] is None and r["warnings"]
