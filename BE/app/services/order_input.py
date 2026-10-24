"""화면에서 새 주문 1건 입력 (api.md: POST /api/sales) [계약변경] 신규

- 주문 CSV(product_return_dataset_2000.csv)의 한 행과 같은 항목을 받습니다.
- 검증은 CSV 업로드와 **같은 규칙**(importers/loader.py 의 _validate)을 그대로 씁니다.
- CSV 업로드(/api/imports)는 표를 통째로 교체하지만, 여기서는 1건만 **추가**합니다.
- 상품명·카테고리는 products 표에서 가져오고, 주문번호는 원본과 같은 형식
  {상품ID}-{YYYYMMDD}-{일련번호 4자리} 로 자동으로 만듭니다.
- 1주문 = 1장 (원본 데이터 quantity 가 모두 1, metrics.md 와 같은 가정)
"""
import sqlite3

from app.errors import validation_failed
from app.importers.loader import NA, _validate

FORM = "입력 폼"


def _next_order_id(conn, product_id: str, day: str) -> str:
    prefix = f"{product_id}-{day.replace('-', '')}-"
    n = 0
    for (oid,) in conn.execute("SELECT order_id FROM sales WHERE order_id LIKE ?", [prefix + "%"]):
        tail = oid[len(prefix):]
        if tail.isdigit():
            n = max(n, int(tail))
    return f"{prefix}{n + 1:04d}"


def _next_return_id(conn) -> str:
    n = 0
    for (rid,) in conn.execute("SELECT return_id FROM returns"):
        if rid and rid[0] == "R" and rid[1:].isdigit():
            n = max(n, int(rid[1:]))
    return f"R{n + 1:04d}"


def add_order(conn: sqlite3.Connection, body: dict) -> dict:
    pid = str(body.get("product_id") or "").strip()
    day = str(body.get("date") or "").strip()
    prod = conn.execute("SELECT product_name, category FROM products WHERE product_id = ?", [pid]).fetchone()
    if prod is None:
        raise validation_failed("입력값을 확인해 주세요",
                                [{"file": FORM, "row": 1, "column": "product_id", "value": pid, "message": "products 에 없는 ID입니다"}])
    returned = body.get("is_returned") in (True, 1, "1", "true", "TRUE")
    rtype = str(body.get("return_type_code") or "").strip()
    rtext = str(body.get("return_detail_text") or "").strip()
    row = {
        "date": day, "product_id": pid, "product_name": prod["product_name"], "category": prod["category"],
        "order_id": _next_order_id(conn, pid, day) if day else "",
        "size": str(body.get("size") or "").strip(), "color": str(body.get("color") or "").strip(),
        "is_returned": "1" if returned else "0",
        "return_type_code": (rtype or NA) if returned else NA,
        "return_detail_text": (rtext or NA) if returned else NA,
    }
    errors, warnings = [], []
    clean = _validate("sales", FORM, [row], {"products": {pid}}, errors, warnings)
    if errors:
        raise validation_failed("입력값을 확인해 주세요", errors)
    r = clean[0]
    conn.execute(
        """INSERT INTO sales (order_id, sold_at, product_id, product_name, category, size, color, qty)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        [r["order_id"], r["date"], r["product_id"], r["product_name"], r["category"], r["size"], r["color"]],
    )
    return_id = None
    if r["is_returned"] == 1:
        return_id = _next_return_id(conn)
        conn.execute(
            """INSERT INTO returns (return_id, order_id, product_id, returned_at, qty,
                                    return_type_code, return_detail_text, resellable)
               VALUES (?, ?, ?, ?, 1, ?, ?, NULL)""",
            [return_id, r["order_id"], r["product_id"], r["date"], r["return_type_code"], r["return_detail_text"]],
        )
    conn.commit()
    return {
        "order": {"order_id": r["order_id"], "date": r["date"], "product_id": r["product_id"],
                  "product_name": r["product_name"], "category": r["category"], "size": r["size"],
                  "color": r["color"], "qty": 1, "is_returned": r["is_returned"],
                  "return_type_code": r["return_type_code"], "return_detail_text": r["return_detail_text"]},
        "return_id": return_id,
        "warnings": warnings,
    }
