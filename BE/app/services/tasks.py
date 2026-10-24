"""개선 조치 저장·조회·수정 (api.md: GET/POST /api/tasks, PATCH /api/tasks/{task_id}).

계산이 없는 기본 CRUD입니다. (Create 만들기 / Read 읽기 / Update 수정 / Delete 삭제)
"""
import sqlite3

from app import enums
from app.errors import not_found, validation_failed
from app.utils import is_date, today_kst

EDITABLE = ["status", "assignee", "due_date", "title"]   # api.md: 변경 가능 필드
DEFAULT_STATUS = "PENDING"


def _product_name(conn, product_id: str) -> str | None:
    row = conn.execute("SELECT product_name FROM products WHERE product_id = ?", [product_id]).fetchone()
    if row is None:   # products.csv 가 아직 없으면 주문 데이터의 상품명을 씁니다
        row = conn.execute("SELECT product_name FROM sales WHERE product_id = ? LIMIT 1", [product_id]).fetchone()
    return row["product_name"] if row else None


def _to_json(conn, row: sqlite3.Row) -> dict:
    return {
        "task_id": row["task_id"],
        "product_id": row["product_id"],
        "product_name": _product_name(conn, row["product_id"]),
        "title": row["title"],
        "type": row["type"],
        "type_label": enums.label("task_types", row["type"]),
        "assignee": row["assignee"],
        "due_date": row["due_date"],
        "status": row["status"],
        "status_label": enums.label("task_statuses", row["status"]),
        "created_at": row["created_at"],
        "source": {"type": row["source_type"], "ref": row["source_ref"]} if row["source_type"] else None,
    }


def _check_fields(data: dict) -> None:
    """코드값·날짜 형식을 검사합니다. 틀리면 400."""
    errors = []
    if "type" in data and enums.codes("task_types") and data["type"] not in enums.codes("task_types"):
        errors.append({"column": "type", "value": str(data["type"]), "message": "정의되지 않은 조치 유형입니다"})
    if "status" in data and data["status"] not in enums.codes("task_statuses"):
        errors.append({"column": "status", "value": str(data["status"]), "message": "정의되지 않은 상태입니다"})
    if data.get("due_date") is not None and not is_date(data["due_date"]):
        errors.append({"column": "due_date", "value": str(data["due_date"]), "message": "날짜는 YYYY-MM-DD 형식이어야 합니다"})
    if "title" in data and not str(data["title"] or "").strip():
        errors.append({"column": "title", "value": "", "message": "제목은 비워둘 수 없습니다"})
    if errors:
        raise validation_failed("요청 값이 올바르지 않습니다", errors)


def _next_id(conn) -> str:
    row = conn.execute("SELECT MAX(CAST(SUBSTR(task_id, 2) AS INTEGER)) AS n FROM tasks").fetchone()
    return f"T{(row['n'] or 0) + 1:04d}"      # T0001, T0002 ...


def create_task(conn, data: dict) -> dict:
    _check_fields(data)
    if _product_name(conn, data["product_id"]) is None:
        raise not_found(f"상품 {data['product_id']} 을(를) 찾을 수 없습니다")

    source = data.get("source") or {}
    task_id = _next_id(conn)
    conn.execute(
        """INSERT INTO tasks (task_id, product_id, title, type, assignee, due_date, status,
                              created_at, source_type, source_ref)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [task_id, data["product_id"], data["title"], data["type"], data.get("assignee"),
         data.get("due_date"), DEFAULT_STATUS, today_kst().isoformat(),
         source.get("type"), source.get("ref")],
    )
    conn.commit()
    return get_task(conn, task_id)


def get_task(conn, task_id: str) -> dict:
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", [task_id]).fetchone()
    if row is None:
        raise not_found(f"조치 {task_id} 을(를) 찾을 수 없습니다")
    return _to_json(conn, row)


def list_tasks(conn, product_id: str | None = None, status: str | None = None) -> dict:
    sql, params = "SELECT * FROM tasks WHERE 1=1", []
    if product_id:
        sql += " AND product_id = ?"
        params.append(product_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    rows = conn.execute(sql + " ORDER BY task_id", params).fetchall()
    return {"items": [_to_json(conn, r) for r in rows]}


def update_task(conn, task_id: str, changes: dict) -> dict:
    get_task(conn, task_id)                  # 없으면 여기서 404
    changes = {k: v for k, v in changes.items() if k in EDITABLE}
    if not changes:
        raise validation_failed("변경할 값이 없습니다. 변경 가능: " + ", ".join(EDITABLE))
    _check_fields(changes)

    sets = ", ".join(f"{k} = ?" for k in changes)
    conn.execute(f"UPDATE tasks SET {sets} WHERE task_id = ?", [*changes.values(), task_id])
    conn.commit()
    return get_task(conn, task_id)
