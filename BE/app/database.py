"""DB 연결.

SQLAlchemy 같은 추가 도구 없이 파이썬에 기본으로 들어 있는 sqlite3를 씁니다.
SQL을 직접 보면서 배울 수 있고, 설치할 것이 줄어듭니다.
"""
import sqlite3

from app.config import db_path
from app.models import SCHEMA_SQL


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row   # row["product_id"] 처럼 이름으로 꺼낼 수 있게
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """테이블이 없으면 만듭니다. 이미 있으면 그대로 둡니다."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_db():
    """FastAPI가 요청마다 DB 연결을 하나 열고, 끝나면 닫아 줍니다."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
