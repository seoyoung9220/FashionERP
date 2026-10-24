"""SQLite 테이블 8개 (BE/README.md "테이블 8개" 그대로).

열 이름은 DATA/dictionary.md 와 똑같이 씁니다. 이름이 곧 계약입니다.
재고 테이블은 만들지 않습니다. 재고는 계산으로 구합니다.
"""

TABLE_NAMES = [
    "products", "suppliers", "purchase_orders", "defects",
    "sales", "returns", "costs", "tasks",
]

SCHEMA_SQL = """
-- 상품: 판매가, 원가, 리드타임, MOQ
CREATE TABLE IF NOT EXISTS products (
    product_id      TEXT PRIMARY KEY,   -- "P001"
    product_name    TEXT NOT NULL,
    category        TEXT,
    price           INTEGER NOT NULL,   -- 원
    cost            INTEGER NOT NULL,   -- 원
    lead_time_days  INTEGER NOT NULL,   -- 일
    moq             INTEGER NOT NULL    -- 장
);

-- 거래처
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     TEXT PRIMARY KEY,   -- "S01"
    supplier_name   TEXT NOT NULL
);

-- 발주·입고·검수·불량 수량
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id           TEXT PRIMARY KEY,   -- "PO2026-0312-01"
    product_id      TEXT NOT NULL,
    supplier_id     TEXT NOT NULL,
    ordered_at      TEXT NOT NULL,      -- "YYYY-MM-DD"
    received_at     TEXT,               -- 미입고면 NULL
    ordered_qty     INTEGER NOT NULL,
    received_qty    INTEGER,
    inspected_qty   INTEGER,            -- 불량률의 분모
    defect_qty      INTEGER
);

-- 불량 유형별 수량
CREATE TABLE IF NOT EXISTS defects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id           TEXT NOT NULL,
    defect_type     TEXT NOT NULL,      -- 영문 코드 (enums.json)
    defect_qty      INTEGER NOT NULL
);

-- 판매: 주문 CSV 한 행 = 한 건 (수량 열이 없어 qty=1)
CREATE TABLE IF NOT EXISTS sales (
    order_id        TEXT PRIMARY KEY,
    sold_at         TEXT NOT NULL,      -- 주문 CSV의 date
    product_id      TEXT NOT NULL,
    product_name    TEXT,
    category        TEXT,
    size            TEXT,
    color           TEXT,
    qty             INTEGER NOT NULL DEFAULT 1,
    channel         TEXT,               -- 주문 CSV에는 없음 → NULL
    amount          INTEGER             -- 주문 CSV에는 없음 → NULL
);

-- 반품: 주문 CSV에서 is_returned=1 인 행
CREATE TABLE IF NOT EXISTS returns (
    return_id           TEXT PRIMARY KEY,   -- "R0001"
    order_id            TEXT NOT NULL UNIQUE,
    product_id          TEXT NOT NULL,
    returned_at         TEXT,               -- 반품일 열이 없어 주문일을 넣음
    qty                 INTEGER NOT NULL DEFAULT 1,
    return_type_code    TEXT,               -- 영문 코드
    return_detail_text  TEXT,               -- 후기 원문 (AI 입력)
    resellable          INTEGER             -- 재판매 가능 1/0, 모르면 NULL
);

-- 비용: product_id "*" = 전체 공통, channel NULL = 전체 채널 공통
CREATE TABLE IF NOT EXISTS costs (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id                      TEXT NOT NULL,
    channel                         TEXT,
    fee_rate_pct                    REAL,       -- 0~100
    ad_cost                         INTEGER,
    shipping_cost_per_order         INTEGER,
    return_handling_cost_per_order  INTEGER     -- 비어 있으면 NULL (0으로 채우지 않음)
);

-- 개선 조치
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,   -- "T0001"
    product_id      TEXT NOT NULL,
    title           TEXT NOT NULL,
    type            TEXT NOT NULL,
    assignee        TEXT,
    due_date        TEXT,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    source_type     TEXT,
    source_ref      TEXT
);
"""
