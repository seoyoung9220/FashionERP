"""재고·발주 계산 (DATA/metrics.md §2 · api.md: GET /api/inventory, GET /api/inventory/reorder).

재고 테이블은 없습니다.
  현재 재고       = Σ 양품 입고 수량 − 판매 주문 수 + 반품 주문 수   (반품은 전량 재고 복귀 가정)
  일평균 판매량    = 최근 N일 주문 수 ÷ N   (N = 7)
  재고 소진 예상일 = 현재 재고 ÷ 일평균 판매량
  발주 필요 시점   = 재고 소진 예상일 − lead_time_days

권장 발주량
  필요 수량  = 일평균 판매량 × (lead_time_days + target_cover_days) − 현재 재고
  불량률 보정 = 필요 수량 ÷ (1 − 상품 평균 불량률 ÷ 100)
  최종 발주량 = ceil(불량률 보정) 을 moq 단위로 올림
"""
import math

from app import enums
from app.utils import note, round1

SALES_WINDOW_DAYS = 7     # metrics.md 기본값
TARGET_COVER_DAYS = 14
OVERSTOCK_DAYS = 60
REORDER_SOON_DAYS = 3


def _ceil(x: float) -> int:
    # 109.70000000001 같은 컴퓨터 계산 오차 때문에 한 칸 더 올라가지 않도록 먼저 다듬습니다
    return math.ceil(round(x, 6))


def calc_stock(cum_good_received: int, sold_order_count: int, returned_order_count: int) -> int:
    return cum_good_received - sold_order_count + returned_order_count


def judge_status(avg_daily_sales, days_to_stockout, reorder_point_days) -> str:
    """metrics.md §2 재고 상태 판정"""
    if not avg_daily_sales or days_to_stockout is None:
        return "UNKNOWN"
    if reorder_point_days < 0:
        return "REORDER_OVERDUE"
    if reorder_point_days <= REORDER_SOON_DAYS:
        return "REORDER_SOON"
    if days_to_stockout > OVERSTOCK_DAYS:
        return "OVERSTOCK"
    return "OK"


def calc_inventory(
    cum_good_received: int,
    sold_order_count: int,
    returned_order_count: int,
    orders_in_window: int,
    sales_window_days: int,
    lead_time_days: int,
    history_days: int | None = None,   # 판매 기록이 있는 기간(일). N보다 짧으면 신뢰도 낮음
) -> dict:
    notes = []
    stock = calc_stock(cum_good_received, sold_order_count, returned_order_count)
    avg = round1(orders_in_window / sales_window_days) if sales_window_days else None

    days_to_stockout = round1(stock / avg) if avg else None
    reorder_point_days = round1(days_to_stockout - lead_time_days) if days_to_stockout is not None else None
    status = judge_status(avg, days_to_stockout, reorder_point_days)
    if days_to_stockout is None:
        notes.append(note("NOT_COMPUTABLE"))

    confidence = "MEDIUM"   # TODO: HIGH 기준은 metrics.md 에 없음 → 시환에게 확인
    if history_days is not None and history_days < sales_window_days:
        confidence = "LOW"
        notes.append(note("LOW_CONFIDENCE"))

    parts = [f"{cum_good_received} − {sold_order_count} + {returned_order_count} = {stock}장"]
    if avg is not None:
        parts.append(f"{orders_in_window} ÷ {sales_window_days} = {avg}장/일")
    if days_to_stockout is not None:
        parts.append(f"{stock} ÷ {avg} = {days_to_stockout}일")
        parts.append(f"{days_to_stockout} − {lead_time_days} = {reorder_point_days}일")

    return {
        "stock_qty": stock,
        "avg_daily_sales": avg,
        "days_to_stockout": days_to_stockout,
        "lead_time_days": lead_time_days,
        "reorder_point_days": reorder_point_days,
        "status": status,
        "status_label": enums.label("inventory_status", status),
        "inputs": {
            "cum_good_received": cum_good_received,
            "sold_order_count": sold_order_count,
            "returned_order_count": returned_order_count,
            "sales_window_days": sales_window_days,
            "orders_in_window": orders_in_window,
        },
        "formula": " · ".join(parts),
        "confidence": confidence,
        "notes": notes,
    }


def calc_reorder(
    avg_daily_sales: float,
    lead_time_days: int,
    target_cover_days: int,
    stock_qty: int,
    defect_rate_pct: float | None,   # 해당 상품 전체 평균 불량률 (급증 판정의 prior_avg_pct 아님)
    moq: int,
) -> dict:
    inputs = {
        "avg_daily_sales": avg_daily_sales,
        "lead_time_days": lead_time_days,
        "target_cover_days": target_cover_days,
        "stock_qty": stock_qty,
        "defect_rate_pct": defect_rate_pct,
        "moq": moq,
    }
    notes = []
    need = avg_daily_sales * (lead_time_days + target_cover_days)
    required_raw = need - stock_qty          # 🔴 재고를 먼저 뺍니다
    formula = f"{avg_daily_sales} × ({lead_time_days} + {target_cover_days}) = {round1(need):g} → − 재고 {stock_qty} = {round1(required_raw):g}"

    if required_raw <= 0:                    # metrics.md: 필요 수량 ≤ 0
        notes.append({"code": None, "message": "현재 재고로 목표 기간 커버 가능"})
        return {"required_qty": 0, "defect_adjusted_qty": 0, "final_order_qty": 0,
                "inputs": inputs, "formula": formula + " → 발주 불필요", "notes": notes}

    if defect_rate_pct is None:              # metrics.md: 상품 평균 불량률이 없으면 보정 생략
        adjusted_raw = required_raw
        notes.append({"code": None, "message": "상품 평균 불량률이 없어 불량률 보정을 생략했습니다"})
        formula += f" → 불량률 보정 생략 = {round1(adjusted_raw):g}"
    else:
        adjusted_raw = required_raw / (1 - defect_rate_pct / 100)
        formula += f" → ÷ (1 − {round(defect_rate_pct / 100, 4):g}) = {round1(adjusted_raw)}"

    adjusted = _ceil(adjusted_raw)                                   # 발주량은 항상 올림
    final = _ceil(adjusted / moq) * moq if moq else adjusted        # MOQ 단위로 올림
    formula += f" → 올림 {adjusted} → MOQ {moq} 단위 올림 = {final}"
    return {
        "required_qty": _ceil(required_raw),
        "defect_adjusted_qty": adjusted,
        "final_order_qty": final,
        "inputs": inputs,
        "formula": formula,
        "notes": notes,
    }
