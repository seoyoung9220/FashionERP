"""api.md 예시 숫자를 그대로 넣었을 때 같은 답이 나오는지 확인합니다.
실행: BE 폴더에서  pytest
"""
from app.services.defect import calc_defect
from app.services.inventory import calc_inventory, calc_reorder
from app.services.profit import calc_contribution
from app.services.returns import calc_return_rate
from app.utils import round1


def test_round_half_up():
    assert round1(0.25) == 0.3          # 파이썬 기본 round(0.25, 1) 은 0.2
    assert round1(28.0047) == 28.0


def test_defect_rate_example():
    r = calc_defect(defect_qty=16, inspected_qty=200, unit_cost=18000,
                    prior_defect_qty=5, prior_inspected_qty=205)
    assert r["defect_rate_pct"] == 8.0
    assert r["defect_loss_amount"] == 288000
    assert r["prior_avg_pct"] == 2.4
    assert r["spike_threshold_pct"] == 3.7
    assert r["is_spike"] is True
    assert r["formula"] == "16 ÷ 200 × 100 = 8.0% · 이전 건 평균 2.4% × 1.5 = 3.7%"


def test_defect_not_computable_is_null_not_zero():
    r = calc_defect(defect_qty=0, inspected_qty=0, unit_cost=18000)
    assert r["defect_rate_pct"] is None
    assert r["notes"][0]["code"] == "NOT_COMPUTABLE"


def test_inventory_example():
    r = calc_inventory(cum_good_received=384, sold_order_count=352, returned_order_count=8,
                       orders_in_window=42, sales_window_days=7, lead_time_days=10)
    assert r["stock_qty"] == 40
    assert r["avg_daily_sales"] == 6.0
    assert r["days_to_stockout"] == 6.7
    assert r["reorder_point_days"] == -3.3


def test_inventory_no_sales_is_null():
    r = calc_inventory(10, 0, 0, orders_in_window=0, sales_window_days=7, lead_time_days=10)
    assert r["days_to_stockout"] is None
    assert r["notes"][0] == {"code": "NOT_COMPUTABLE", "message": "산출 불가"}


def test_reorder_example():
    r = calc_reorder(avg_daily_sales=6.0, lead_time_days=10, target_cover_days=14,
                     stock_qty=40, defect_rate_pct=5.2, moq=50)
    assert (r["required_qty"], r["defect_adjusted_qty"], r["final_order_qty"]) == (104, 110, 150)
    assert r["formula"] == "6.0 × (10 + 14) = 144 → − 재고 40 = 104 → ÷ (1 − 0.052) = 109.7 → 올림 110 → MOQ 50 단위 올림 = 150"


def test_profit_example():
    r = calc_contribution(3818000, {
        "cost_of_goods": 1584000, "platform_fee": 381800, "defect_loss": 288000,
        "ad_cost": 250000, "shipping_cost": 176000, "return_handling_cost": 69000,
    })
    assert r["contribution_margin"] == 1069200
    assert r["contribution_margin_pct"] == 28.0
    assert r["is_negative"] is False
    assert [(b["key"], b["share_pct"]) for b in r["cost_breakdown"]] == [
        ("cost_of_goods", 57.6), ("platform_fee", 13.9), ("ad_cost", 9.1),
        ("shipping_cost", 6.4), ("return_handling_cost", 2.5), ("defect_loss", 10.5),
    ]
    assert r["formula"] == "3,818,000 − 1,584,000 − 381,800 − 495,000 − 288,000 = 1,069,200원 (28.0%)"


def test_profit_missing_cost_is_not_zero():
    r = calc_contribution(1000000, {"cost_of_goods": 400000, "platform_fee": 100000, "ad_cost": None,
                                    "shipping_cost": 50000, "return_handling_cost": 10000, "defect_loss": 0})
    assert r["ad_cost"] is None
    assert r["missing_costs"] == ["ad_cost"]
    assert r["notes"] == [{"code": "MISSING_COST", "message": "일부 비용 미입력"}]


def test_return_rate_example_p002():
    r = calc_return_rate(277, 57, {"SIZE_FIT": 22, "CHANGE_OF_MIND": 18, "QUALITY_FINISH": 5,
                                   "COLOR_IMAGE": 5, "SHIPPING": 3, "OTHER": 2,
                                   "FABRIC_FEEL": 1, "DEFECTIVE": 1})
    assert r["return_rate_pct"] == 20.6
    assert r["formula"] == "57 ÷ 277 × 100 = 20.6%"
    assert [x["share_pct"] for x in r["reasons"]] == [38.6, 31.6, 8.8, 8.8, 5.3, 3.5, 1.8, 1.8]
    assert r["reasons"][0]["label"] == "사이즈·핏 문제"
    assert r["notes"] == []


def test_return_rate_small_sample():
    r = calc_return_rate(259, 6, {"SIZE_FIT": 6})
    assert r["notes"][0]["code"] == "SMALL_SAMPLE"


# ── DATA/metrics.md 예외 규칙 ──

def test_spike_is_greater_or_equal():
    # 이전 평균 2.0% × 1.5 = 3.0%, 현재 3.0% → metrics.md 는 "≥" 이므로 급증
    r = calc_defect(defect_qty=3, inspected_qty=100, unit_cost=1000, prior_defect_qty=2, prior_inspected_qty=100)
    assert r["is_spike"] is True


def test_no_prior_po_is_not_spike_and_small_sample():
    r = calc_defect(defect_qty=16, inspected_qty=200, unit_cost=18000)
    assert r["is_spike"] is False
    assert r["notes"][0]["code"] == "SMALL_SAMPLE"


def test_inventory_status_rules():
    r = calc_inventory(384, 352, 8, orders_in_window=42, sales_window_days=7, lead_time_days=10)
    assert (r["status"], r["status_label"]) == ("REORDER_OVERDUE", "발주 시점 경과")
    r = calc_inventory(1000, 0, 0, orders_in_window=7, sales_window_days=7, lead_time_days=10)
    assert r["status"] == "OVERSTOCK"
    r = calc_inventory(10, 0, 0, orders_in_window=0, sales_window_days=7, lead_time_days=10)
    assert r["status"] == "UNKNOWN"


def test_reorder_enough_stock_is_zero():
    r = calc_reorder(1.0, 10, 14, stock_qty=100, defect_rate_pct=5.0, moq=50)
    assert r["final_order_qty"] == 0
    assert r["notes"][0]["message"] == "현재 재고로 목표 기간 커버 가능"


def test_reorder_without_defect_rate_skips_correction():
    r = calc_reorder(6.0, 10, 14, stock_qty=40, defect_rate_pct=None, moq=50)
    assert (r["defect_adjusted_qty"], r["final_order_qty"]) == (104, 150)


def test_profit_amounts_from_metrics_formula():
    from app.services.profit import calc_profit
    r = calc_profit(sold_order_count=10, returned_order_count=2, price=10000, unit_cost=4000,
                    fee_rate_pct=10.0, ad_cost=5000, shipping_cost_per_order=3000,
                    return_handling_cost_per_order=None, defect_qty=1)
    # 순매출 80,000 − 원가 32,000 − 수수료 8,000 − (광고 5,000 + 배송 30,000) − 불량 4,000 = 1,000
    assert (r["gross_sales"], r["return_amount"], r["net_sales"]) == (100000, 20000, 80000)
    assert r["contribution_margin"] == 1000
    assert r["missing_costs"] == ["return_handling_cost"]


def test_profit_zero_net_sales_is_null():
    from app.services.profit import calc_profit
    r = calc_profit(0, 0, 10000, 4000, 10.0, 0, 3000, 5000, 0)
    assert r["contribution_margin_pct"] is None
    assert any(n["code"] == "NOT_COMPUTABLE" for n in r["notes"])
