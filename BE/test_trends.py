"""홈 매출 흐름 · 판매 비교 · 재고자산 · 월별 수익 · 카테고리 비중 — 팀 실제 데이터로 검증.
기대값은 원본 CSV 로 따로 계산한 값입니다 (DATA/expected/expected-metrics.md 월별 표와도 대조)."""
from datetime import date

import pytest

from app.database import connect, init_db
from app.importers.loader import seed_if_empty
from app.services.profit_query import profit
from app.services.trends import category_sales, daily_sales, inventory_value, monthly_profit, sales_momentum

AS_OF = date(2026, 10, 24)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()


def test_daily_sales_last_7_days(conn):
    r = daily_sales(conn, "2026-10-18", "2026-10-24")
    assert [i["net_sales"] for i in r["items"]] == [840000, 834000, 378000, 823000, 950000, 592000, 477000]
    assert r["total"] == {"order_count": 58, "gross_sales": 5533000, "net_sales": 4894000}
    assert all(i["net_sales"] == i["gross_sales"] - i["return_amount"] for i in r["items"])


def test_daily_sales_outside_data_is_null_not_zero(conn):
    r = daily_sales(conn, "2030-01-01", "2030-01-02")
    assert all(i["net_sales"] is None for i in r["items"])
    assert r["notes"][0]["code"] == "NOT_COMPUTABLE"


def test_momentum_reports_change_but_never_judges_surge(conn):
    r = sales_momentum(conn, AS_OF)
    by = {i["product_id"]: (i["current_orders"], i["previous_orders"], i["change_pct"]) for i in r["items"]}
    assert by["P001"] == (15, 4, 275.0) and by["P008"] == (4, 8, -50.0)
    assert r["rule_defined"] is False and all(i["is_surge"] is None for i in r["items"])


def test_inventory_value_is_stock_times_cost(conn):
    r = inventory_value(conn, AS_OF)
    assert (r["total_qty"], r["total_value"]) == (234, 9160000)
    p1 = next(i for i in r["items"] if i["product_id"] == "P001")
    assert (p1["stock_qty"], p1["unit_cost"], p1["stock_value"]) == (32, 82000, 2624000)


def test_monthly_matches_team_table_and_sums_to_profit(conn):
    r = monthly_profit(conn, "2026-01-10", "2026-10-24")
    m = {i["month"]: i for i in r["items"]}
    assert len(m) == 10 and m["2026-01"]["partial"] and m["2026-10"]["partial"] and not m["2026-05"]["partial"]
    # expected-metrics.md 월별 표와 같은 항목 (총매출·반품 금액·순매출·원가·수수료·배송+반품비)
    jan = m["2026-01"]
    assert (jan["gross_sales"], jan["return_amount"], jan["net_sales"], jan["cost_of_goods"], jan["platform_fee"],
            jan["shipping_cost"] + jan["return_handling_cost"]) == (12538000, 1156000, 11382000, 5227000, 1138200, 550000)
    # 불량 손실은 metrics.md §3 대로 입고월(received_at) 기준
    assert {k: v["defect_loss"] for k, v in m.items() if v["defect_loss"]} == {
        "2026-02": 92000, "2026-06": 46000, "2026-08": 322000, "2026-09": 1015000, "2026-10": 92000}
    # 월별(광고비 제외) 합계 − 광고비 = 같은 기간 /api/profit 기여이익 합
    whole = sum(p["contribution_margin"] for p in profit(conn, "2026-01-10", "2026-10-24"))
    assert r["total"]["contribution_margin"] == whole == 52545500
    assert r["total"]["ad_cost"] == 1050000 and r["total"]["missing_costs"] == ["ad_cost"]


def test_category_share_uses_net_sales_and_sums_to_total(conn):
    r = category_sales(conn, "2026-01-10", "2026-10-24")
    by = {i["category"]: (i["net_sales"], i["share_pct"]) for i in r["items"]}
    assert by == {"아우터": (92867000, 65.9), "하의/치마": (26534000, 18.8), "상의/셔츠": (21574000, 15.3)}
    assert r["total"]["net_sales"] == 140975000 and r["total"]["check_sum_net_sales"] is True
    r30 = category_sales(conn, "2026-09-25", "2026-10-24")
    assert r30["total"]["net_sales"] == 15485000      # /api/profit 30일 순매출 합과 같음
