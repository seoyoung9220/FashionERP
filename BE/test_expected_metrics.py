"""DATA/expected/expected-metrics.md 의 기대값과 1:1 대조 (팀 실제 데이터 사용)."""
import pytest

from app.database import connect, init_db
from app.importers.loader import seed_if_empty
from app.services import stock
from app.services.dashboard import summary
from app.services.profit_query import profit
from app.services.quality import defect_rates
from app.utils import data_as_of, period_ending


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()


def test_defect_rates(conn):
    po = {i["po_id"]: i for i in defect_rates(conn)}
    assert len(po) == 10
    assert (po["PO2026-1012-01"]["defect_rate_pct"], po["PO2026-1012-01"]["prior_avg_pct"],
            po["PO2026-1012-01"]["spike_threshold_pct"], po["PO2026-1012-01"]["is_spike"]) == (8.0, 3.0, 4.5, True)
    assert (po["PO2026-0618-01"]["prior_avg_pct"], po["PO2026-0618-01"]["is_spike"]) == (3.3, False)
    assert po["PO2026-0905-01"]["defect_loss_amount"] == 410000
    assert sum(i["is_spike"] for i in po.values()) == 1
    sup = {i["supplier_id"]: i["defect_rate_pct"] for i in defect_rates(conn, "supplier")}
    assert sup == {"S01": 2.3, "S02": 2.0, "S03": 2.2}


def test_inventory(conn):
    inv = {i["product_id"]: (i["stock_qty"], i["avg_daily_sales"], i["days_to_stockout"],
                             i["reorder_point_days"], i["status"]) for i in stock.inventory(conn, data_as_of(conn))}
    assert inv["P001"] == (32, 2.1, 15.2, -5.8, "REORDER_OVERDUE")
    assert inv["P002"] == (20, 1.4, 14.3, 0.3, "REORDER_SOON")
    assert inv["P003"] == (66, 0.7, 94.3, 76.3, "OVERSTOCK")
    assert inv["P008"] == (32, 0.6, 53.3, 39.3, "OK")


def test_reorder(conn):
    ro = {i["product_id"]: (i["required_qty"], i["defect_adjusted_qty"], i["final_order_qty"])
          for i in stock.reorder(conn, data_as_of(conn))}
    assert ro["P001"] == (42, 43, 60)
    assert ro["P002"] == (20, 20, 50)
    assert ro["P004"] == (6, 6, 40)
    assert ro["P003"] == (0, 0, 0)


def test_profit(conn):
    f, t = period_ending(data_as_of(conn), 30)
    assert (f, t) == ("2026-09-25", "2026-10-24")
    p = {i["product_id"]: i for i in profit(conn, f, t)}
    assert (p["P001"]["contribution_margin"], p["P001"]["contribution_margin_pct"]) == (2620300, 42.0)
    assert (p["P002"]["contribution_margin"], p["P002"]["defect_loss"]) == (228400, 92000)
    assert (p["P007"]["contribution_margin"], p["P007"]["contribution_margin_pct"]) == (-21600, -2.9)
    assert p["P007"]["missing_costs"] == ["ad_cost"] and p["P007"]["is_negative"] is True


def test_dashboard_matches_mock_numbers(conn):
    a = data_as_of(conn)
    d = summary(conn, a, *period_ending(a, 30))
    assert d["defect"]["defect_rate_pct"] == 2.1 and d["defect"]["spike_count"] == 1
    assert d["inventory"] == {"reorder_overdue_count": 1, "reorder_soon_count": 1, "overstock_count": 1, "ok_count": 5}
    assert d["profit"] == {"contribution_margin": 5092500, "contribution_margin_pct": 32.9, "negative_product_count": 1}
    assert d["returns"]["return_rate_pct"] == 9.2
    assert d["returns"]["top_actionable_reason"]["code"] == "SIZE_FIT"
