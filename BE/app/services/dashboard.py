"""홈 대시보드 요약 (api.md: GET /api/dashboard · FE/src/mocks/dashboard.json).

다른 API의 계산 결과를 그대로 불러와 요약만 합니다. 새 공식은 없습니다.
- defect: 전체 발주 건 기준 (불량률 = Σ불량 ÷ Σ검수), 급증 건수, 불량률이 가장 높은 거래처
- inventory: 재고 상태별 상품 수
- profit: 기간(최근 30일) 합계 추정 기여이익, 적자 상품 수
- returns: 전체 기간 반품률, 사유 1위, "고칠 수 있는" 사유 1위(단순 변심·기타 제외), 반품률 최고 상품
  ※ FE 목업의 숫자(9.2%, 단순 변심 33.7% 등)가 전체 기간 기준이라 그에 맞췄습니다
"""
from collections import Counter

from app import enums
from app.services import stock
from app.services.profit_query import profit
from app.services.quality import by_po, defect_rates
from app.utils import note, pct

NOT_ACTIONABLE = {"CHANGE_OF_MIND", "OTHER"}


def summary(conn, as_of, date_from: str, date_to: str) -> dict:
    notes = []

    tot = conn.execute("SELECT SUM(defect_qty), SUM(inspected_qty) FROM purchase_orders WHERE inspected_qty > 0").fetchone()
    suppliers = defect_rates(conn, "supplier")
    worst = suppliers[0] if suppliers and suppliers[0]["defect_rate_pct"] is not None else None
    defect = {
        "defect_rate_pct": pct(tot[0] or 0, tot[1]) if tot[1] else None,
        "spike_count": sum(1 for i in by_po(conn) if i["is_spike"]),
        "worst_supplier": {k: worst[k] for k in ("supplier_id", "supplier_name", "defect_rate_pct", "po_count")} if worst else None,
    }

    status = Counter(i["status"] for i in stock.inventory(conn, as_of))
    inventory = {"reorder_overdue_count": status["REORDER_OVERDUE"], "reorder_soon_count": status["REORDER_SOON"],
                 "overstock_count": status["OVERSTOCK"], "ok_count": status["OK"]}

    items = profit(conn, date_from, date_to)
    net = sum(i["net_sales"] for i in items)
    margin = sum(i["contribution_margin"] for i in items)
    profit_box = {"contribution_margin": margin if items else None,
                  "contribution_margin_pct": pct(margin, net) if net else None,
                  "negative_product_count": sum(1 for i in items if i["is_negative"])}
    if any(i["missing_costs"] for i in items):
        notes.append(note("MISSING_COST"))

    orders = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    reasons = Counter(r[0] for r in conn.execute("SELECT return_type_code FROM returns WHERE return_type_code IS NOT NULL ORDER BY rowid"))
    n_ret = sum(reasons.values())

    def box(code):
        return {"code": code, "label": enums.label("return_types", code), "share_pct": pct(reasons[code], n_ret)} if code else None

    top = reasons.most_common(1)[0][0] if reasons else None
    actionable = next((c for c, _ in reasons.most_common() if c not in NOT_ACTIONABLE), None)
    per_product = conn.execute(
        """SELECT s.product_id, MAX(s.product_name) name, COUNT(*) o, COUNT(r.return_id) rc
           FROM sales s LEFT JOIN returns r ON r.order_id = s.order_id GROUP BY s.product_id""").fetchall()
    wp = max(per_product, key=lambda r: r["rc"] / r["o"]) if per_product else None
    returns = {
        "return_rate_pct": pct(conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0], orders) if orders else None,
        "top_reason": box(top),
        "top_actionable_reason": box(actionable),
        "worst_product": {"product_id": wp["product_id"], "product_name": wp["name"],
                          "return_rate_pct": pct(wp["rc"], wp["o"])} if wp else None,
    }
    return {"as_of": as_of.isoformat(), "period": {"from": date_from, "to": date_to},
            "defect": defect, "inventory": inventory, "profit": profit_box, "returns": returns, "notes": notes}
