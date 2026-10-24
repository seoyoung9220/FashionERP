"""재고·발주량 조회 (DATA/metrics.md §2 · api.md: GET /api/inventory, GET /api/inventory/reorder).

DB에서 숫자를 모아 inventory.py 의 계산 함수에 넘깁니다.

- 현재 재고 = Σ 양품 입고(received_qty − defect_qty) − 판매 주문 수 + 반품 주문 수
- 발주(입고) 기록이 하나도 없으면 재고를 알 수 없으므로
  stock_qty 등은 null + NOT_COMPUTABLE, status: UNKNOWN (CONVENTIONS §7: 0을 쓰지 않음)
- 상품 목록은 products 테이블, 없으면 주문 데이터의 상품을 씁니다
"""
from datetime import date, timedelta

from app import enums
from app.services.inventory import calc_inventory, calc_reorder
from app.services.quality import product_avg_defect_rate
from app.utils import note, round1


def _products(conn) -> list[dict]:
    rows = conn.execute("SELECT product_id, product_name, lead_time_days, moq FROM products ORDER BY product_id").fetchall()
    if rows:
        return [dict(r) for r in rows]
    rows = conn.execute("SELECT product_id, MAX(product_name) product_name FROM sales GROUP BY product_id ORDER BY product_id")
    return [{"product_id": r[0], "product_name": r[1], "lead_time_days": None, "moq": None} for r in rows]


def _numbers(conn, product_id: str, as_of: date, window: int) -> dict:
    po = conn.execute(
        """SELECT COUNT(*) n, SUM(received_qty - COALESCE(defect_qty, 0)) good
           FROM purchase_orders WHERE product_id = ? AND received_at IS NOT NULL AND received_qty IS NOT NULL""",
        [product_id],
    ).fetchone()
    sold = conn.execute("SELECT COUNT(*), MIN(sold_at) FROM sales WHERE product_id = ? AND sold_at <= ?",
                        [product_id, as_of.isoformat()]).fetchone()
    returned = conn.execute(
        "SELECT COUNT(*) FROM returns r JOIN sales s ON s.order_id = r.order_id WHERE s.product_id = ? AND s.sold_at <= ?",
        [product_id, as_of.isoformat()]).fetchone()[0]
    start = (as_of - timedelta(days=window - 1)).isoformat()
    in_window = conn.execute("SELECT COUNT(*) FROM sales WHERE product_id = ? AND sold_at BETWEEN ? AND ?",
                             [product_id, start, as_of.isoformat()]).fetchone()[0]
    history = (as_of - date.fromisoformat(sold[1])).days + 1 if sold[1] else 0
    return {
        "has_po": po["n"] > 0,
        "cum_good_received": po["good"] or 0,
        "sold": sold[0],
        "returned": returned,
        "in_window": in_window,
        "history_days": history,
    }


def _not_computable_inventory(p: dict, n: dict, window: int) -> dict:
    return {
        "product_id": p["product_id"],
        "product_name": p["product_name"],
        "stock_qty": None,
        # 재고는 몰라도 판매량은 주문 데이터로 계산할 수 있으므로 보여줍니다
        "avg_daily_sales": round1(n["in_window"] / window),
        "days_to_stockout": None,
        "lead_time_days": p["lead_time_days"],
        "reorder_point_days": None,
        "status": "UNKNOWN",
        "status_label": enums.label("inventory_status", "UNKNOWN"),
        "inputs": {
            "cum_good_received": None,
            "sold_order_count": n["sold"],
            "returned_order_count": n["returned"],
            "sales_window_days": window,
            "orders_in_window": n["in_window"],
        },
        "formula": "산출 불가 (입고 기록 또는 상품 정보 없음)",
        "confidence": "LOW",
        "notes": [note("NOT_COMPUTABLE")],
    }


def inventory(conn, as_of: date, window: int = 7) -> list[dict]:
    items = []
    for p in _products(conn):
        n = _numbers(conn, p["product_id"], as_of, window)
        if not n["has_po"] or p["lead_time_days"] is None:
            items.append(_not_computable_inventory(p, n, window))
            continue
        calc = calc_inventory(n["cum_good_received"], n["sold"], n["returned"], n["in_window"],
                              window, p["lead_time_days"], n["history_days"])
        items.append({"product_id": p["product_id"], "product_name": p["product_name"], **calc})
    return items


def reorder(conn, as_of: date, target_cover_days: int = 14, window: int = 7) -> list[dict]:
    items = []
    for inv, p in zip(inventory(conn, as_of, window), _products(conn)):
        base = {"product_id": p["product_id"], "product_name": p["product_name"]}
        avg = inv["avg_daily_sales"]
        if inv["stock_qty"] is None or avg is None or p["moq"] is None:
            items.append({
                **base,
                "required_qty": None, "defect_adjusted_qty": None, "final_order_qty": None,
                "inputs": {"avg_daily_sales": avg, "lead_time_days": p["lead_time_days"],
                           "target_cover_days": target_cover_days, "stock_qty": inv["stock_qty"],
                           "defect_rate_pct": product_avg_defect_rate(conn, p["product_id"]), "moq": p["moq"]},
                "formula": "산출 불가 (재고 또는 일평균 판매량을 알 수 없음)",
                "confidence": inv["confidence"],
                "notes": [note("NOT_COMPUTABLE")],
            })
            continue
        calc = calc_reorder(avg, p["lead_time_days"], target_cover_days, inv["stock_qty"],
                            product_avg_defect_rate(conn, p["product_id"]), p["moq"])
        notes = [n for n in inv["notes"] if n.get("code") == "LOW_CONFIDENCE"] + calc["notes"]
        items.append({**base, **{k: calc[k] for k in ("required_qty", "defect_adjusted_qty", "final_order_qty",
                                                     "inputs", "formula")},
                      "confidence": inv["confidence"], "notes": notes})
    return items
