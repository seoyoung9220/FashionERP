"""수익성 조회 (DATA/metrics.md §3 · api.md: GET /api/profit).

DB에서 기간 안의 주문·반품 수, 상품 가격·원가, 비용 설정, 불량 수량을 모아
profit.py 의 calc_profit 에 넘깁니다.

- 주문·반품: 주문일(sold_at)이 기간 안인 건
- 불량 손실: 기간 안에 입고(received_at)된 발주 건의 defect_qty × 원가
- 비용: costs.csv 에서 해당 상품 행 → 없거나 비어 있으면 product_id "*" (전체 공통) 행
  그래도 비어 있으면 0으로 채우지 않고 missing_costs 로 보냅니다
"""
from app.services.profit import calc_profit

COST_FIELDS = ["fee_rate_pct", "ad_cost", "shipping_cost_per_order", "return_handling_cost_per_order"]
INPUT_KEYS = ["sold_order_count", "returned_order_count", "unit_cost", "price", "fee_rate_pct", "defect_qty"]  # FE 목업과 같은 키


def _cost_settings(conn, product_id: str) -> dict:
    rows = {r["product_id"]: dict(r) for r in conn.execute(
        "SELECT * FROM costs WHERE product_id IN (?, '*') AND channel IS NULL", [product_id])}
    own, common = rows.get(product_id, {}), rows.get("*", {})
    return {f: own.get(f) if own.get(f) is not None else common.get(f) for f in COST_FIELDS}


def profit(conn, date_from: str, date_to: str) -> list[dict]:
    items = []
    for p in conn.execute("SELECT * FROM products ORDER BY product_id").fetchall():
        pid = p["product_id"]
        sold = conn.execute("SELECT COUNT(*) FROM sales WHERE product_id = ? AND sold_at BETWEEN ? AND ?",
                            [pid, date_from, date_to]).fetchone()[0]
        returned = conn.execute(
            """SELECT COUNT(*) FROM returns r JOIN sales s ON s.order_id = r.order_id
               WHERE s.product_id = ? AND s.sold_at BETWEEN ? AND ?""", [pid, date_from, date_to]).fetchone()[0]
        defect = conn.execute(
            """SELECT COALESCE(SUM(defect_qty), 0) FROM purchase_orders
               WHERE product_id = ? AND received_at BETWEEN ? AND ?""", [pid, date_from, date_to]).fetchone()[0]
        c = _cost_settings(conn, pid)
        r = calc_profit(sold, returned, p["price"], p["cost"], c["fee_rate_pct"], c["ad_cost"],
                        c["shipping_cost_per_order"], c["return_handling_cost_per_order"], defect)
        r["inputs"] = {k: r["inputs"][k] for k in INPUT_KEYS}
        items.append({"product_id": pid, "product_name": p["product_name"], **r})
    return items
