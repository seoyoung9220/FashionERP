"""추이·구성 집계 — 홈 매출 흐름 · 판매 비교 · 재고자산 · 월별 수익 · 카테고리 비중.

🔴 새 공식을 만들지 않습니다. 금액은 모두 DATA/metrics.md §3 정의를 그대로 씁니다.
   - 매출(총매출) = 주문 수 × products.price · 반품 금액 = 반품 주문 수 × price · 순매출 = 총매출 − 반품 금액
   - 월별·카테고리 기여이익은 기존 profit_query.profit() 을 기간·상품별로 불러 더합니다.
   - 재고 수량은 기존 stock.inventory() 결과(metrics.md §2)를 그대로 씁니다.
주문 1건 = 1장, 반품일 열이 없어 반품은 주문일 기준입니다 (metrics.md §2·§4 와 같은 가정).
"""
import calendar
from datetime import date, timedelta

from app.services import stock
from app.services.profit_query import profit
from app.utils import fmt_num, note, pct


def _f(x) -> str:
    """formula 표시용 — 값이 없으면 0 이 아니라 '—'"""
    return "—" if x is None else fmt_num(x)

# 월별 추이에서 '기간 전체에 한 번 드는' 광고비를 어떻게 다룰지 — metrics.md 에 월 배분 규칙이 없습니다.
# 매달 전액을 빼면 10배로 부풀려지므로, 월별 값은 광고비를 빼기 전(광고비 제외) 값으로 보여주고
# 합계에서 한 번만 뺍니다 → 합계는 같은 기간 /api/profit 결과와 정확히 같습니다.
AD_NOTE = {"code": None, "message": "광고비(ad_cost)는 월 배분 규칙이 없어 월별 값에서 제외하고 합계에서 한 번만 뺐습니다"}


def _dates(date_from: str, date_to: str):
    d, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    while d <= end:
        yield d
        d += timedelta(days=1)


# ───────────────────────── A. 일별 매출 (홈 '매출 흐름') ─────────────────────────

def daily_sales(conn, date_from: str, date_to: str) -> dict:
    rows = {r["d"]: r for r in conn.execute(
        """SELECT s.sold_at AS d, COUNT(*) AS orders, COUNT(r.return_id) AS returns,
                  SUM(p.price) AS gross, SUM(CASE WHEN r.return_id IS NULL THEN 0 ELSE p.price END) AS ret_amt,
                  SUM(CASE WHEN p.price IS NULL THEN 1 ELSE 0 END) AS no_price
           FROM sales s JOIN products p ON p.product_id = s.product_id
           LEFT JOIN returns r ON r.order_id = s.order_id
           WHERE s.sold_at BETWEEN ? AND ? GROUP BY s.sold_at""", [date_from, date_to])}
    has_sales = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] > 0
    items = []
    for d in _dates(date_from, date_to):
        r = rows.get(d.isoformat())
        if r is None:   # 그날 주문이 없음 = 실제 0건 (데이터 범위 밖이면 null)
            in_range = has_sales and conn.execute(
                "SELECT MIN(sold_at) <= ? AND MAX(sold_at) >= ? FROM sales", [d.isoformat()] * 2).fetchone()[0]
            v = 0 if in_range else None
            items.append({"date": d.isoformat(), "order_count": v, "return_count": v, "gross_sales": v,
                          "return_amount": v, "net_sales": v,
                          "inputs": {"order_count": v, "return_count": v},
                          "formula": "주문 0건" if v == 0 else "데이터 기간 밖",
                          "notes": [] if v == 0 else [note("NOT_COMPUTABLE")]})
            continue
        net = r["gross"] - r["ret_amt"]
        items.append({
            "date": d.isoformat(), "order_count": r["orders"], "return_count": r["returns"],
            "gross_sales": r["gross"], "return_amount": r["ret_amt"], "net_sales": net,
            "inputs": {"order_count": r["orders"], "return_count": r["returns"]},
            "formula": f"총매출 {_f(r['gross'])} − 반품 {_f(r['ret_amt'])} = 순매출 {_f(net)}원",
            "notes": [],
        })
    known = [i for i in items if i["net_sales"] is not None]
    return {"period": {"from": date_from, "to": date_to}, "basis": "order_date",
            "total": {"order_count": sum(i["order_count"] for i in known),
                      "gross_sales": sum(i["gross_sales"] for i in known),
                      "net_sales": sum(i["net_sales"] for i in known)},
            "items": items,
            "formula": "일별 순매출 = Σ(그날 주문 × 판매가) − Σ(그날 주문 중 반품 × 판매가)",
            "notes": [] if known else [note("NOT_COMPUTABLE")]}


# ───────────────────────── B. 판매 비교 (판매 급증 '참고값') ─────────────────────────

SUGGESTED_RULE = ("제안(미적용): 최근 7일 주문 ≥ 직전 7일 주문 × 1.5 이고 직전 7일 주문 ≥ 5건 "
                  "— 불량률 급증과 같은 1.5배 기준. metrics.md 에 판매 급증 정의가 없어 팀 합의 전에는 판정하지 않습니다")


def sales_momentum(conn, as_of: date, window: int = 7) -> dict:
    cur_from, cur_to = (as_of - timedelta(days=window - 1)).isoformat(), as_of.isoformat()
    prev_from, prev_to = (as_of - timedelta(days=2 * window - 1)).isoformat(), (as_of - timedelta(days=window)).isoformat()
    first = conn.execute("SELECT MIN(sold_at) FROM sales").fetchone()[0]
    enough_history = first is not None and first <= prev_from
    items = []
    for p in conn.execute("SELECT product_id, product_name, category FROM products ORDER BY product_id"):
        cnt = lambda a, b: conn.execute(
            "SELECT COUNT(*) FROM sales WHERE product_id = ? AND sold_at BETWEEN ? AND ?", [p["product_id"], a, b]).fetchone()[0]
        cur, prev = cnt(cur_from, cur_to), cnt(prev_from, prev_to)
        notes = []
        if not enough_history:
            notes.append({"code": "LOW_CONFIDENCE", "message": "직전 비교 기간의 판매 기록이 없습니다"})
        change_pct = pct(cur - prev, prev) if prev else None
        if prev == 0:
            notes.append(note("NOT_COMPUTABLE"))
        items.append({
            "product_id": p["product_id"], "product_name": p["product_name"], "category": p["category"],
            "current_orders": cur, "previous_orders": prev, "change": cur - prev, "change_pct": change_pct,
            "is_surge": None,   # 기준 미정 — 판정하지 않음
            "inputs": {"current_period": {"from": cur_from, "to": cur_to}, "previous_period": {"from": prev_from, "to": prev_to}},
            "formula": (f"({cur} − {prev}) ÷ {prev} × 100 = {change_pct}%" if prev else f"직전 기간 0건 → 증가율 산출 불가 (최근 {cur}건)"),
            "notes": notes,
        })
    items.sort(key=lambda x: (-(x["change_pct"] if x["change_pct"] is not None else -1e9), x["product_id"]))
    return {"as_of": as_of.isoformat(), "window_days": window, "basis": "order_count",
            "current_period": {"from": cur_from, "to": cur_to}, "previous_period": {"from": prev_from, "to": prev_to},
            "rule_defined": False, "suggested_rule": SUGGESTED_RULE, "items": items,
            "notes": [{"code": None, "message": "판매 급증 기준이 metrics.md 에 없어 증가율만 제공하고 급증 여부는 판정하지 않습니다"}]}


# ───────────────────────── C. 전체 재고자산 ─────────────────────────

def inventory_value(conn, as_of: date) -> dict:
    cost = {r["product_id"]: r["cost"] for r in conn.execute("SELECT product_id, cost FROM products")}
    items, excluded = [], []
    for i in stock.inventory(conn, as_of):
        q, c = i["stock_qty"], cost.get(i["product_id"])
        if q is None or c is None:
            excluded.append({"product_id": i["product_id"], "reason": "재고 수량 산출 불가" if q is None else "원가 미입력"})
            v, notes = None, [note("NOT_COMPUTABLE")]
        else:
            v, notes = q * c, ([{"code": None, "message": "재고가 음수입니다 — 입고·주문 데이터를 확인하세요"}] if q < 0 else [])
        items.append({"product_id": i["product_id"], "product_name": i["product_name"], "stock_qty": q,
                      "unit_cost": c, "stock_value": v,
                      "inputs": {"stock_qty": q, "unit_cost": c},
                      "formula": f"{_f(q)}장 × {_f(c)}원 = {_f(v)}원" if v is not None else "산출 불가",
                      "notes": notes})
    known = [i for i in items if i["stock_value"] is not None]
    total_qty = sum(i["stock_qty"] for i in items if i["stock_qty"] is not None)
    total_value = sum(i["stock_value"] for i in known) if known else None
    return {"as_of": as_of.isoformat(), "basis": "cost", "total_qty": total_qty, "total_value": total_value,
            "excluded": excluded, "items": items,
            "inputs": {"product_count": len(items), "valued_product_count": len(known)},
            "formula": f"Σ(상품별 현재 재고 × 원가) = {_f(total_value)}원 · 재고 {_f(total_qty)}장"
                       if total_value is not None else "산출 불가",
            "notes": [{"code": None, "message": "원가(products.cost) 기준 평가 · 반품은 전량 재고 복귀 가정 (metrics.md §2)"}]
                     + ([note("NOT_COMPUTABLE")] if total_value is None else [])}


# ───────────────────────── D. 월별 매출·추정 기여이익 ─────────────────────────

SUM_KEYS = ["gross_sales", "return_amount", "net_sales", "cost_of_goods", "platform_fee",
            "shipping_cost", "return_handling_cost", "defect_loss"]


def _sum(items, key):
    vals = [i[key] for i in items if i.get(key) is not None]
    return sum(vals) if vals else None


def monthly_profit(conn, date_from: str, date_to: str) -> dict:
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    months, d = [], start.replace(day=1)
    while d <= end:
        last = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        m_from, m_to = max(d, start), min(last, end)
        prods = profit(conn, m_from.isoformat(), m_to.isoformat())       # 기존 계산 재사용
        row = {k: _sum(prods, k) for k in SUM_KEYS}
        ad = sum(p["ad_cost"] or 0 for p in prods)
        excl = sum(p["contribution_margin"] for p in prods) + ad           # 광고비를 빼기 전 값
        row.update({
            "month": d.strftime("%Y-%m"), "from": m_from.isoformat(), "to": m_to.isoformat(),
            "partial": m_from != d or m_to != last,
            "order_count": sum(p["inputs"]["sold_order_count"] for p in prods),
            "return_count": sum(p["inputs"]["returned_order_count"] for p in prods),
            "contribution_margin_excl_ad": excl,
            "contribution_margin_excl_ad_pct": pct(excl, row["net_sales"]) if row["net_sales"] else None,
        })
        row["inputs"] = {k: row[k] for k in ("order_count", "return_count", "net_sales", "cost_of_goods", "platform_fee",
                                             "shipping_cost", "return_handling_cost", "defect_loss")}
        row["formula"] = (f"{_f(row['net_sales'])} − {_f(row['cost_of_goods'])} − {_f(row['platform_fee'])}"
                          f" − {_f((row['shipping_cost'] or 0) + (row['return_handling_cost'] or 0))}"
                          f" − {_f(row['defect_loss'])} = {_f(excl)}원 (광고비 제외)")
        row["notes"] = []
        months.append(row)
        d = last + timedelta(days=1)

    whole = profit(conn, date_from, date_to)
    ad_total = sum(p["ad_cost"] or 0 for p in whole)
    missing = sorted({k for p in whole for k in p["missing_costs"]})
    total_excl = sum(m["contribution_margin_excl_ad"] for m in months)
    total_net = sum(m["net_sales"] or 0 for m in months)
    margin = total_excl - ad_total
    notes = [AD_NOTE] + ([note("MISSING_COST")] if missing else [])
    if any(m["partial"] for m in months):
        notes.append({"code": None, "message": "처음·마지막 달은 데이터가 있는 날짜까지만 집계했습니다 (partial: true)"})
    return {
        "period": {"from": date_from, "to": date_to}, "items": months,
        "total": {"gross_sales": sum(m["gross_sales"] or 0 for m in months), "net_sales": total_net,
                  "contribution_margin_excl_ad": total_excl, "ad_cost": ad_total,
                  "contribution_margin": margin, "contribution_margin_pct": pct(margin, total_net) if total_net else None,
                  "missing_costs": missing},
        "formula": f"Σ 월별(광고비 제외) {_f(total_excl)} − 광고비 {_f(ad_total)} = 추정 기여이익 {_f(margin)}원",
        "notes": notes,
    }


# ───────────────────────── E. 카테고리별 매출 비중 ─────────────────────────

def category_sales(conn, date_from: str, date_to: str) -> dict:
    cat = {r["product_id"]: r["category"] for r in conn.execute("SELECT product_id, category FROM products")}
    groups: dict[str, list] = {}
    for p in profit(conn, date_from, date_to):                              # 기존 계산 재사용
        groups.setdefault(cat.get(p["product_id"]) or "미분류", []).append(p)
    total_net = sum(p["net_sales"] for ps in groups.values() for p in ps)
    total_gross = sum(p["gross_sales"] for ps in groups.values() for p in ps)
    items = []
    for name, ps in groups.items():
        net, gross = sum(p["net_sales"] for p in ps), sum(p["gross_sales"] for p in ps)
        margin = sum(p["contribution_margin"] for p in ps)
        missing = sorted({k for p in ps for k in p["missing_costs"]})
        items.append({
            "category": name, "product_count": len(ps), "product_ids": [p["product_id"] for p in ps],
            "order_count": sum(p["inputs"]["sold_order_count"] for p in ps),
            "gross_sales": gross, "net_sales": net, "share_pct": pct(net, total_net) if total_net else None,
            "gross_share_pct": pct(gross, total_gross) if total_gross else None,
            "contribution_margin": margin, "contribution_margin_pct": pct(margin, net) if net else None,
            "missing_costs": missing,
            "inputs": {"net_sales": net, "total_net_sales": total_net},
            "formula": f"{_f(net)} ÷ {_f(total_net)} × 100 = {pct(net, total_net) if total_net else None}%",
            "notes": ([note("MISSING_COST")] if missing else []) + ([{"code": None, "message": "카테고리 미입력 상품"}] if name == "미분류" else []),
        })
    items.sort(key=lambda x: -x["net_sales"])
    return {"period": {"from": date_from, "to": date_to}, "basis": "net_sales",
            "total": {"net_sales": total_net, "gross_sales": total_gross, "category_count": len(items),
                      "check_sum_net_sales": sum(i["net_sales"] for i in items) == total_net},
            "items": items,
            "formula": "카테고리 비중 = 카테고리 순매출 ÷ 전체 순매출 × 100 (순매출 = 총매출 − 반품 금액, metrics.md §3)",
            "notes": [] if total_net else [note("NOT_COMPUTABLE")]}
