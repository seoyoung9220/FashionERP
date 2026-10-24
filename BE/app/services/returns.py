"""반품률 (api.md: GET /api/returns/rates).

주문 단위 데이터라 전부 "건수" 기준입니다 (basis: "count").
명세 예시: 57 ÷ 277 × 100 = 20.6%  ← 주문 CSV 전체 기간의 실제 P002 값
"""
import sqlite3

from app import enums
from app.utils import note, pct

SMALL_SAMPLE_RETURNS = 10   # CONVENTIONS §7: 반품 10건 미만이면 표본 부족


def calc_return_rate(order_count: int, return_count: int, reason_counts: dict[str, int]) -> dict:
    rate = pct(return_count, order_count)
    notes = []
    if rate is None:
        notes.append(note("NOT_COMPUTABLE"))
    elif return_count < SMALL_SAMPLE_RETURNS:
        notes.append(note("SMALL_SAMPLE"))

    reasons = [
        {
            "code": code,
            "label": enums.label("return_types", code) or code,
            "count": cnt,
            "share_pct": pct(cnt, return_count),
        }
        # 건수 많은 순. 동률이면 데이터(CSV)에 먼저 나온 사유가 앞 (api.md 예시·expected-metrics.md 기준)
        for code, cnt in sorted(reason_counts.items(), key=lambda kv: -kv[1])
    ]
    return {
        "order_count": order_count,
        "return_count": return_count,
        "return_rate_pct": rate,
        "basis": "count",
        "reasons": reasons,
        "inputs": {"order_count": order_count, "return_count": return_count},
        "formula": f"{return_count} ÷ {order_count} × 100 = {rate}%" if rate is not None else "산출 불가",
        "notes": notes,
    }


def return_rates(conn: sqlite3.Connection, date_from: str, date_to: str, product_id: str | None = None) -> dict:
    """기간 안의 주문(주문일 기준)을 상품별로 묶어 반품률을 구합니다."""
    where = "s.sold_at BETWEEN ? AND ?"
    params: list = [date_from, date_to]
    if product_id:
        where += " AND s.product_id = ?"
        params.append(product_id)

    orders = conn.execute(
        f"""
        SELECT s.product_id,
               MAX(s.product_name) AS product_name,
               COUNT(*)            AS order_count,
               COUNT(r.return_id)  AS return_count
        FROM sales s
        LEFT JOIN returns r ON r.order_id = s.order_id
        WHERE {where}
        GROUP BY s.product_id
        """,
        params,
    ).fetchall()

    reason_rows = conn.execute(
        f"""
        SELECT s.product_id, COALESCE(r.return_type_code, 'OTHER') AS code, COUNT(*) AS cnt,
               MIN(r.rowid) AS first_seen
        FROM returns r
        JOIN sales s ON s.order_id = r.order_id
        WHERE {where}
        GROUP BY s.product_id, code
        ORDER BY s.product_id, first_seen
        """,
        params,
    ).fetchall()
    # TODO: 반품 사유 코드가 비어 있는 반품을 OTHER로 볼지 DATA팀(시환)과 확인

    reasons: dict[str, dict[str, int]] = {}
    for row in reason_rows:
        reasons.setdefault(row["product_id"], {})[row["code"]] = row["cnt"]

    items = []
    for row in orders:
        calc = calc_return_rate(row["order_count"], row["return_count"], reasons.get(row["product_id"], {}))
        items.append({"product_id": row["product_id"], "product_name": row["product_name"], **calc})

    items.sort(key=lambda x: (-(x["return_rate_pct"] or 0), x["product_id"]))
    return {"period": {"from": date_from, "to": date_to}, "items": items}
