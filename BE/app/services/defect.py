"""불량률 계산 (api.md: GET /api/quality/defect-rates).

이 파일의 함수는 "숫자를 받아서 결과를 돌려주는" 순수 계산만 합니다.
DB를 몰라도 되므로, api.md 예시 숫자를 넣어 정답과 비교할 수 있습니다.

명세 예시: 16 ÷ 200 × 100 = 8.0% · 이전 건 평균 2.4% × 1.5 = 3.7% 초과
"""
from app.utils import note, pct, to_won

SPIKE_MULTIPLIER = 1.5     # api.md 예시 기준. 최종 값은 DATA/metrics.md 확인
SMALL_SAMPLE_INSPECTED = 30  # CONVENTIONS §7: 검수 수량 30 미만이면 표본 부족


def calc_defect(
    defect_qty: int | None,
    inspected_qty: int | None,
    unit_cost: int | None,
    prior_defect_qty: int | None = None,
    prior_inspected_qty: int | None = None,
) -> dict:
    notes = []

    # 분모는 검수 수량 (received_qty 아님!)
    rate_raw = (defect_qty / inspected_qty * 100) if inspected_qty else None
    rate = pct(defect_qty or 0, inspected_qty) if inspected_qty else None
    if rate is None:
        notes.append(note("NOT_COMPUTABLE"))
    elif inspected_qty < SMALL_SAMPLE_INSPECTED:
        notes.append(note("SMALL_SAMPLE"))

    loss = to_won(defect_qty * unit_cost) if (defect_qty is not None and unit_cost is not None) else None

    # 급증 판정: 이전 건 평균 × 1.5 를 넘으면 급증
    prior_raw = (prior_defect_qty / prior_inspected_qty * 100) if prior_inspected_qty else None
    prior_avg = pct(prior_defect_qty or 0, prior_inspected_qty) if prior_inspected_qty else None
    threshold_raw = prior_raw * SPIKE_MULTIPLIER if prior_raw is not None else None
    threshold = pct(threshold_raw, 100) if threshold_raw is not None else None
    # metrics.md: is_spike = (입고 불량률 ≥ spike_threshold_pct)
    if rate_raw is not None and threshold_raw is not None:
        is_spike = rate_raw >= threshold_raw
    else:
        # metrics.md: 이전 발주 건이 없으면 is_spike: false + SMALL_SAMPLE
        is_spike = False
        if rate is not None and not prior_inspected_qty and not any(n["code"] == "SMALL_SAMPLE" for n in notes):
            notes.append(note("SMALL_SAMPLE"))

    formula = "산출 불가"
    if rate is not None:
        formula = f"{defect_qty} ÷ {inspected_qty} × 100 = {rate}%"
        if threshold is not None:
            formula += f" · 이전 건 평균 {prior_avg}% × {SPIKE_MULTIPLIER} = {threshold}%"   # FE 목업 문구와 같음
        else:
            formula += " · 이전 발주 건 없음"   # FE 목업 문구와 같음

    return {
        "defect_rate_pct": rate,
        "defect_loss_amount": loss,
        "prior_avg_pct": prior_avg,
        "spike_threshold_pct": threshold,
        "is_spike": is_spike,
        "inputs": {
            "defect_qty": defect_qty,
            "inspected_qty": inspected_qty,
            "unit_cost": unit_cost,
            "prior_defect_qty": prior_defect_qty,
            "prior_inspected_qty": prior_inspected_qty,
        },
        "formula": formula,
        "notes": notes,
    }


def share_list(counts: dict[str, int], label_fn) -> list[dict]:
    """{"SEWING": 11, ...} → [{"code","label","qty","share_pct"}, ...] (많은 순)"""
    total = sum(counts.values())
    items = sorted(counts.items(), key=lambda kv: -kv[1])   # 같은 수량이면 CSV에 적힌 순서 유지 (FE 목업과 같음)
    return [
        {"code": c, "label": label_fn(c), "qty": q, "share_pct": pct(q, total)}
        for c, q in items
    ]

