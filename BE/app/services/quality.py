"""불량률 조회 (DATA/metrics.md §1 · api.md: GET /api/quality/defect-rates).

DB에서 발주(purchase_orders)·불량 유형(defects)·상품·거래처를 꺼내
defect.py 의 계산 함수에 넘깁니다.

- 분모는 inspected_qty (검수 수량)
- 급증 판정 기준: 같은 상품의 "이전" 발주 건들(received_at 이 더 이른 건)의 평균
  ※ metrics.md 는 "해당 발주 건을 제외한 이전 발주 건들"이라고만 되어 있어,
    같은 상품 기준으로 해석했습니다. (작업노트에 확인 요청)
- 발주 데이터가 없으면 items: [] (CONVENTIONS §7: 빈 목록은 [])
"""
from app import enums
from app.services.defect import calc_defect, share_list
from app.utils import note, pct, to_won

GROUPS = ("po", "product", "supplier")


def _names(conn, table, key, name):
    return {r[0]: r[1] for r in conn.execute(f"SELECT {key}, {name} FROM {table}")}


def _po_rows(conn, product_id=None, supplier_id=None):
    sql, params = "SELECT * FROM purchase_orders WHERE 1=1", []
    if product_id:
        sql += " AND product_id = ?"
        params.append(product_id)
    if supplier_id:
        sql += " AND supplier_id = ?"
        params.append(supplier_id)
    return conn.execute(sql + " ORDER BY received_at, po_id", params).fetchall()


def _unit_costs(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT product_id, cost FROM products")}


def by_po(conn, product_id=None, supplier_id=None) -> list[dict]:
    products = _names(conn, "products", "product_id", "product_name")
    suppliers = _names(conn, "suppliers", "supplier_id", "supplier_name")
    costs = _unit_costs(conn)
    all_rows = _po_rows(conn)                       # 이전 건 계산은 필터와 무관하게 전체에서
    wanted = {r["po_id"] for r in _po_rows(conn, product_id, supplier_id)}

    types: dict[str, dict[str, int]] = {}
    for d in conn.execute("SELECT po_id, defect_type, SUM(defect_qty) q FROM defects GROUP BY po_id, defect_type ORDER BY MIN(id)"):
        types.setdefault(d["po_id"], {})[d["defect_type"]] = d["q"]

    items = []
    for po in all_rows:
        if po["po_id"] not in wanted:
            continue
        prior = [
            p for p in all_rows
            if p["product_id"] == po["product_id"] and p["po_id"] != po["po_id"]
            and p["received_at"] and po["received_at"] and p["received_at"] < po["received_at"]
            and p["inspected_qty"]
        ]
        prior_d = sum(p["defect_qty"] or 0 for p in prior)    # 이전 건이 없으면 0 (실제로 0건, FE 목업과 같음)
        prior_i = sum(p["inspected_qty"] for p in prior)

        calc = calc_defect(po["defect_qty"], po["inspected_qty"], costs.get(po["product_id"]), prior_d, prior_i)
        good = (po["received_qty"] - po["defect_qty"]) if (po["received_qty"] is not None and po["defect_qty"] is not None) else None
        items.append({
            "po_id": po["po_id"],
            "product_id": po["product_id"],
            "product_name": products.get(po["product_id"]),
            "supplier_id": po["supplier_id"],
            "supplier_name": suppliers.get(po["supplier_id"]),
            "received_at": po["received_at"],
            "received_qty": po["received_qty"],
            "inspected_qty": po["inspected_qty"],
            "defect_qty": po["defect_qty"],
            "good_qty": good,
            "defect_rate_pct": calc["defect_rate_pct"],
            "defect_loss_amount": calc["defect_loss_amount"],
            "prior_avg_pct": calc["prior_avg_pct"],
            "spike_threshold_pct": calc["spike_threshold_pct"],
            "is_spike": calc["is_spike"],
            "defect_types": share_list(types.get(po["po_id"], {}), lambda c: enums.label("defect_types", c) or c),
            "inputs": calc["inputs"],
            "formula": calc["formula"],
            "notes": calc["notes"],
        })
    return items


def _grouped(conn, key: str, product_id=None, supplier_id=None) -> list[dict]:
    """상품 평균 / 거래처 불량률 = Σ defect_qty ÷ Σ inspected_qty × 100"""
    names = (_names(conn, "products", "product_id", "product_name") if key == "product_id"
             else _names(conn, "suppliers", "supplier_id", "supplier_name"))
    costs = _unit_costs(conn)
    groups: dict[str, list] = {}
    for po in _po_rows(conn, product_id, supplier_id):
        groups.setdefault(po[key], []).append(po)

    items = []
    for gid, rows in groups.items():
        insp = [r for r in rows if r["inspected_qty"]]
        sum_d = sum(r["defect_qty"] or 0 for r in insp)
        sum_i = sum(r["inspected_qty"] for r in insp)
        rate = pct(sum_d, sum_i) if sum_i else None
        loss_parts = [(r["defect_qty"] or 0) * costs[r["product_id"]] for r in insp if r["product_id"] in costs]
        loss = to_won(sum(loss_parts)) if len(loss_parts) == len(insp) else None

        notes = []
        if rate is None:
            notes.append(note("NOT_COMPUTABLE"))
        elif sum_i < 30:
            notes.append(note("SMALL_SAMPLE"))

        item = {key: gid}
        item["product_name" if key == "product_id" else "supplier_name"] = names.get(gid)
        if key == "supplier_id":
            item["po_count"] = len(rows)
        item.update({
            "inspected_qty": sum_i,
            "defect_qty": sum_d,
            "defect_rate_pct": rate,
            "defect_loss_amount": loss,
            "inputs": {"defect_qty": sum_d, "inspected_qty": sum_i, "po_count": len(rows)},
            "formula": f"{sum_d} ÷ {sum_i} × 100 = {rate}%" if rate is not None else "산출 불가",
            "notes": notes,
        })
        items.append(item)
    items.sort(key=lambda x: -(x["defect_rate_pct"] or 0))
    return items


def defect_rates(conn, group_by="po", product_id=None, supplier_id=None) -> list[dict]:
    if group_by == "po":
        return by_po(conn, product_id, supplier_id)
    return _grouped(conn, "product_id" if group_by == "product" else "supplier_id", product_id, supplier_id)


def product_avg_defect_rate(conn, product_id: str) -> float | None:
    """발주량 보정용: 해당 상품 전체 평균 불량률. 검수 기록이 없으면 None."""
    r = conn.execute(
        "SELECT SUM(defect_qty), SUM(inspected_qty) FROM purchase_orders WHERE product_id = ? AND inspected_qty > 0",
        [product_id],
    ).fetchone()
    return pct(r[0] or 0, r[1]) if r[1] else None
