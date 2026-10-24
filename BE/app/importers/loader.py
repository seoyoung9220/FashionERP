"""CSV 읽기 → 검증(12개 규칙) → DB 적재 (DATA/dictionary.md §3).

규칙 1  필수 열이 없으면 → 400 VALIDATION_FAILED, 파일 전체 거부 (아무것도 저장 안 함)
규칙 2~8, 10, 12  → 그 행만 errors 에 담고 나머지는 적재
규칙 9, 11        → warnings 에 담고 적재는 진행

업로드한 테이블은 "통째로 교체"합니다. (같은 파일을 두 번 올려도 중복되지 않게)
"""
import csv
import io
import re
import sqlite3

from app import enums
from app.config import ORDERS_CSV, SAMPLE_DIR
from app.errors import AppError, validation_failed
from app.importers.specs import ORDER, SAMPLE_FILES, SPECS
from app.utils import is_date

KEY_COLUMN = {"products": "product_id", "suppliers": "supplier_id", "purchase_orders": "po_id", "sales": "order_id"}
NA = "NA"


# ───────────────────────── 1. CSV 읽기 ─────────────────────────

def read_csv(raw: bytes) -> tuple[list[str], list[dict]]:
    # 🔴 엑셀 CSV의 BOM 때문에 반드시 utf-8-sig 로 읽습니다
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    header = [(h or "").strip() for h in (reader.fieldnames or [])]
    rows = []
    for r in reader:
        rows.append({(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
    return header, rows


def strip_quotes(text: str | None) -> str | None:
    """'지퍼 윗부분이 뻑뻑해서...' → 지퍼 윗부분이 뻑뻑해서..."""
    if text and len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].strip()
    return text


# ───────────────────────── 2. 값 하나 검사 ─────────────────────────

def parse_value(kind: str, raw: str):
    """(변환된 값, 오류 문구 또는 None)"""
    if kind in ("id", "str"):
        return raw, None
    if kind in ("qty", "won"):
        if re.fullmatch(r"\d+", raw):
            return int(raw), None
        word = "수량" if kind == "qty" else "금액"
        return None, f"{word}은 0 이상의 정수여야 합니다"           # 규칙 3
    if kind == "date":
        if is_date(raw):
            return raw, None
        return None, "날짜는 YYYY-MM-DD 형식이어야 합니다"          # 규칙 5
    if kind == "pct":
        try:
            v = float(raw)
        except ValueError:
            v = -1
        if 0 <= v <= 100:
            return v, None
        return None, "비율은 0~100 사이 숫자여야 합니다"            # 규칙 4
    if kind == "bool01":
        mapping = {"0": 0, "1": 1, "FALSE": 0, "TRUE": 1}
        if raw.upper() in mapping:
            return mapping[raw.upper()], None
        return None, "0 또는 1 이어야 합니다"
    if kind.startswith("enum:"):
        group = kind.split(":", 1)[1]
        if not enums.codes(group):          # enums.json 에 그룹이 없으면 그대로 받음
            return raw, None
        code = enums.to_code(group, raw)
        if code:
            return code, None
        return None, "enums.json 에 정의되지 않은 값입니다"          # 규칙 6
    raise ValueError(kind)


# ───────────────────────── 3. 파일 하나 검사 ─────────────────────────

def _validate(name: str, fname: str, rows: list[dict], known: dict, errors: list, warnings: list) -> list[dict]:
    clean, seen = [], set()

    for i, row in enumerate(rows):
        line = i + 2                              # 엑셀에서 보이는 행 번호 (1행 = 헤더)
        row_errs = []

        def err(col, value, msg):
            row_errs.append({"file": fname, "row": line, "column": col, "value": value, "message": msg})

        if name == "sales":
            row["return_detail_text"] = strip_quotes(row.get("return_detail_text"))

        values = {}
        for col, kind, required in SPECS[name]:
            raw = row.get(col)
            if name == "sales" and col in ("return_type_code", "return_detail_text") and raw == NA:
                values[col] = None                # 문자열 "NA" → null (0이 아님)
                continue
            if raw in (None, ""):
                if required:
                    err(col, raw or "", "필수 값이 비어 있습니다")   # 규칙 2
                values[col] = None
                continue
            value, msg = parse_value(kind, raw)
            if msg:
                err(col, raw, msg)
            values[col] = value

        if not row_errs:
            _cross_check(name, values, known, seen, err, warnings, fname, line)

        if row_errs:
            errors.extend(row_errs)
            continue
        clean.append(values)
        if name in KEY_COLUMN:
            seen.add(values[KEY_COLUMN[name]])
    return clean


def _cross_check(name, v, known, seen, err, warnings, fname, line):
    # 규칙 10: 중복 ID
    key = KEY_COLUMN.get(name)
    if key and v[key] in seen:
        err(key, v[key], "같은 ID가 이미 있습니다")

    # 규칙 7, 12: 참조 ID가 실제로 존재
    def must_exist(col, table):
        if v[col] not in known[table]:
            err(col, v[col], f"{table} 에 없는 ID입니다")

    if name == "purchase_orders":
        must_exist("product_id", "products")
        must_exist("supplier_id", "suppliers")
        # 규칙 8: defect_qty ≤ inspected_qty ≤ received_qty ≤ ordered_qty (값이 있는 것끼리 비교)
        chain = [c for c in ["defect_qty", "inspected_qty", "received_qty", "ordered_qty"] if v[c] is not None]
        for small, big in zip(chain, chain[1:]):
            if v[small] > v[big]:
                err(small, str(v[small]), f"{small} 은(는) {big} 보다 클 수 없습니다")
    elif name == "defects":
        must_exist("po_id", "purchase_orders")
    elif name == "costs":
        if v["product_id"] != "*":            # "*" = 전체 상품 공통
            must_exist("product_id", "products")
    elif name == "sales":
        if known["products"]:
            must_exist("product_id", "products")   # 규칙 12
        if v["is_returned"] == 1 and v["return_type_code"] is None:   # 규칙 11
            warnings.append({"file": fname, "row": line, "message": f"{v['order_id']} 은(는) 반품인데 반품 유형이 NA입니다"})


# ───────────────────────── 4. DB에 쓰기 ─────────────────────────

def _write(conn: sqlite3.Connection, name: str, rows: list[dict]) -> dict:
    if name == "sales":
        conn.execute("DELETE FROM returns")
        conn.execute("DELETE FROM sales")
        n_ret = 0
        for r in rows:
            conn.execute(
                """INSERT INTO sales (order_id, sold_at, product_id, product_name, category, size, color, qty)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                [r["order_id"], r["date"], r["product_id"], r["product_name"], r["category"], r["size"], r["color"]],
            )
            if r["is_returned"] == 1:
                n_ret += 1
                conn.execute(
                    """INSERT INTO returns (return_id, order_id, product_id, returned_at, qty,
                                            return_type_code, return_detail_text, resellable)
                       VALUES (?, ?, ?, ?, 1, ?, ?, NULL)""",
                    [f"R{n_ret:04d}", r["order_id"], r["product_id"], r["date"],
                     r["return_type_code"], r["return_detail_text"]],
                )
        return {"sales": len(rows), "returns": n_ret}

    cols = [c for c, _, _ in SPECS[name]]
    conn.execute(f"DELETE FROM {name}")
    conn.executemany(
        f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [[r[c] for c in cols] for r in rows],
    )
    return {name: len(rows)}


def _ids(conn, table, col) -> set:
    return {r[0] for r in conn.execute(f"SELECT {col} FROM {table}")}


def _check_defect_sums(conn, warnings):
    """규칙 9: 같은 po_id 의 defects 합계 = purchase_orders.defect_qty (다르면 경고만)"""
    rows = conn.execute(
        """SELECT p.po_id, p.defect_qty, SUM(d.defect_qty) AS total
           FROM purchase_orders p JOIN defects d ON d.po_id = p.po_id
           GROUP BY p.po_id"""
    ).fetchall()
    for r in rows:
        if r["defect_qty"] is not None and r["total"] != r["defect_qty"]:
            warnings.append({"file": "defects.csv",
                             "message": f"{r['po_id']}의 불량 유형 합계가 발주 건 불량 수량과 다릅니다"})


# ───────────────────────── 5. 전체 흐름 ─────────────────────────

def import_files(conn: sqlite3.Connection, files: dict[str, tuple[str, bytes]]) -> dict:
    """files = {"products": ("products.csv", 바이트), "sales": (...), ...}"""
    unknown = [k for k in files if k not in SPECS]
    if unknown:
        raise validation_failed(
            "알 수 없는 업로드 필드입니다. 사용 가능: " + ", ".join(ORDER),
            [{"file": k, "message": "필드 이름은 테이블 이름이어야 합니다"} for k in unknown],
        )

    # 먼저 모든 파일의 열을 확인합니다. 하나라도 빠지면 아무것도 저장하지 않습니다 (규칙 1)
    parsed, missing = {}, []
    for name in ORDER:
        if name not in files:
            continue
        fname, raw = files[name]
        try:
            header, rows = read_csv(raw)
        except UnicodeDecodeError:
            missing.append({"file": fname, "message": "UTF-8 CSV 파일이 아닙니다"})
            continue
        for col, _, required in SPECS[name]:
            if required and col not in header:
                missing.append({"file": fname, "row": 1, "column": col, "value": None, "message": "필수 열이 없습니다"})
        parsed[name] = (fname, rows)
    if missing:
        raise validation_failed(f"업로드 파일에서 {len(missing)}개의 열 오류를 발견했습니다", missing)

    known = {
        "products": _ids(conn, "products", "product_id"),
        "suppliers": _ids(conn, "suppliers", "supplier_id"),
        "purchase_orders": _ids(conn, "purchase_orders", "po_id"),
    }
    errors, warnings, imported = [], [], {}
    try:
        for name in ORDER:
            if name not in parsed:
                continue
            fname, rows = parsed[name]
            if name == "sales" and not known["products"]:
                warnings.append({"file": fname, "message": "products.csv 가 아직 없어 상품 ID 확인(규칙 12)을 건너뛰었습니다"})
            clean = _validate(name, fname, rows, known, errors, warnings)
            imported.update(_write(conn, name, clean))
            if name in known:     # 다음 파일의 참조 확인에 쓰도록 갱신
                known[name] = {r[KEY_COLUMN[name]] for r in clean}
        if "defects" in parsed or "purchase_orders" in parsed:
            _check_defect_sums(conn, warnings)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # api.md 예시에는 imported, warnings 만 있습니다. 행 오류를 알려줄 errors 는
    # [계약변경] 으로 팀에 공유 후 api.md 와 mock 에 추가해야 합니다.
    return {"imported": imported, "warnings": warnings, "errors": errors}


def seed_if_empty(conn: sqlite3.Connection) -> dict | None:
    """앱 시작 시 DB가 비어 있으면 데모 데이터를 자동으로 넣습니다.
    (업로드가 실패해도 시연이 되어야 합니다 - BE/README.md)"""
    if conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] > 0:
        return None
    files = {}
    for name, fname in SAMPLE_FILES.items():
        path = SAMPLE_DIR / fname
        if path.exists():
            files[name] = (fname, path.read_bytes())
    if ORDERS_CSV.exists():
        files["sales"] = (ORDERS_CSV.name, ORDERS_CSV.read_bytes())
    if not files:
        print("[seed] 데모 데이터 파일이 없어 건너뜁니다")
        return None
    try:
        result = import_files(conn, files)
    except AppError as e:
        print(f"[seed] 실패: {e.message} {e.details}")
        return None
    print(f"[seed] 적재 완료: {result['imported']} · 행 오류 {len(result['errors'])}건 · 경고 {len(result['warnings'])}건")
    return result
