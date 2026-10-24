"""수익(기여이익) 계산 (api.md: GET /api/profit).

명세 예시
  3,818,000 - 1,584,000 - 381,800 - 495,000 - 288,000 = 1,069,200원 (28.0%)
  = 순매출 - 상품원가 - 플랫폼 수수료 - (광고비+배송비+반품처리비) - 불량 손실

비어 있는 비용은 0으로 채우지 않습니다. 계산에서 빼고 missing_costs와 notes에 남깁니다.

금액 산출 (DATA/metrics.md §3, 주문 1건 = 1장, 정가 판매 가정)
  총매출 = 판매 주문 수 × price · 반품 금액 = 반품 주문 수 × price · 순매출 = 총매출 − 반품 금액
  상품 원가 = (판매 − 반품) × cost · 수수료 = 순매출 × fee_rate_pct ÷ 100
  배송비 = 판매 × shipping_cost_per_order · 반품 처리비 = 반품 × return_handling_cost_per_order
  불량 손실 = Σ defect_qty × cost
🔴 "순이익"이 아니라 "추정 기여이익"입니다.
"""
from app.utils import fmt_num, note, pct, to_won

COST_LABELS = {
    "cost_of_goods": "상품 원가",
    "platform_fee": "플랫폼 수수료",
    "defect_loss": "불량 손실",
    "ad_cost": "광고비",
    "shipping_cost": "배송비",
    "return_handling_cost": "반품 처리비",
}
BREAKDOWN_ORDER = ["cost_of_goods", "platform_fee", "ad_cost", "shipping_cost", "return_handling_cost", "defect_loss"]
# 공식에서 하나로 묶어 쓰는 운영비
OPERATING = ["ad_cost", "shipping_cost", "return_handling_cost"]


def calc_profit(
    sold_order_count: int,
    returned_order_count: int,
    price: int,
    unit_cost: int,
    fee_rate_pct: float | None,
    ad_cost: int | None,
    shipping_cost_per_order: int | None,
    return_handling_cost_per_order: int | None,
    defect_qty: int,
) -> dict:
    """주문 수와 단가·비용 설정을 받아 금액을 만든 뒤 기여이익을 계산합니다."""
    gross = sold_order_count * price
    return_amount = returned_order_count * price
    net = gross - return_amount
    costs = {
        "cost_of_goods": (sold_order_count - returned_order_count) * unit_cost,
        "platform_fee": None if fee_rate_pct is None else to_won(net * fee_rate_pct / 100),
        "ad_cost": ad_cost,
        "shipping_cost": None if shipping_cost_per_order is None else sold_order_count * shipping_cost_per_order,
        "return_handling_cost": None if return_handling_cost_per_order is None
        else returned_order_count * return_handling_cost_per_order,
        "defect_loss": defect_qty * unit_cost,
    }
    result = calc_contribution(net, costs)
    return {
        "gross_sales": gross,
        "return_amount": return_amount,
        **result,
        "inputs": {
            "sold_order_count": sold_order_count,
            "returned_order_count": returned_order_count,
            "unit_cost": unit_cost,
            "price": price,
            "fee_rate_pct": fee_rate_pct,
            "ad_cost": ad_cost,
            "shipping_cost_per_order": shipping_cost_per_order,
            "return_handling_cost_per_order": return_handling_cost_per_order,
            "defect_qty": defect_qty,
        },
    }


def calc_contribution(net_sales: int, costs: dict[str, int | None]) -> dict:
    """costs 예: {"cost_of_goods": 1584000, "platform_fee": 381800, "ad_cost": None, ...}"""
    missing = [k for k in COST_LABELS if costs.get(k) is None]
    present = {k: to_won(costs[k]) for k in COST_LABELS if costs.get(k) is not None}

    total_cost = sum(present.values())
    margin = net_sales - total_cost
    margin_pct = pct(margin, net_sales)

    # FE 목업과 같은 순서(공식 순서), 0원 항목은 빼고 보여줍니다
    breakdown = [
        {"key": k, "label": COST_LABELS[k], "amount": present[k], "share_pct": pct(present[k], total_cost)}
        for k in BREAKDOWN_ORDER if present.get(k)
    ]

    terms = [fmt_num(net_sales)]
    for k in ["cost_of_goods", "platform_fee"]:
        if k in present:
            terms.append(fmt_num(present[k]))
    op = [present[k] for k in OPERATING if k in present]
    if op:
        terms.append(fmt_num(sum(op)))
    if "defect_loss" in present:
        terms.append(fmt_num(present["defect_loss"]))
    formula = " − ".join(terms) + f" = {fmt_num(margin)}원 ({margin_pct}%)"

    notes = [note("MISSING_COST")] if missing else []
    if margin_pct is None:                    # metrics.md: 순매출 = 0
        notes.append(note("NOT_COMPUTABLE"))
    return {
        "net_sales": net_sales,
        **{k: present.get(k) for k in COST_LABELS},
        "contribution_margin": margin,
        "contribution_margin_pct": margin_pct,
        "is_negative": margin < 0,
        "cost_breakdown": breakdown,
        "missing_costs": missing,
        "formula": formula,
        "notes": notes,
    }
