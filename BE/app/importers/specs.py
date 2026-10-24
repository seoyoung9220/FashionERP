"""CSV 열 정의 (DATA/dictionary.md 그대로).

(열 이름, 자료형, 필수 여부)
자료형: id/str 문자열 · qty 수량(0 이상 정수) · won 금액(0 이상 정수)
        date YYYY-MM-DD · pct 비율 0~100 · enum:<그룹> 열거형 · bool01 0/1
"""

SPECS = {
    "products": [
        ("product_id", "id", True),
        ("product_name", "str", True),
        ("category", "str", False),
        ("price", "won", True),
        ("cost", "won", True),
        ("lead_time_days", "qty", True),
        ("moq", "qty", True),
    ],
    "suppliers": [
        ("supplier_id", "id", True),
        ("supplier_name", "str", True),
    ],
    "purchase_orders": [
        ("po_id", "id", True),
        ("product_id", "id", True),
        ("supplier_id", "id", True),
        ("ordered_at", "date", True),
        ("received_at", "date", False),
        ("ordered_qty", "qty", True),
        ("received_qty", "qty", False),
        ("inspected_qty", "qty", False),
        ("defect_qty", "qty", False),
    ],
    "defects": [
        ("po_id", "id", True),
        ("defect_type", "enum:defect_types", True),
        ("defect_qty", "qty", True),
    ],
    "costs": [
        ("product_id", "id", True),
        ("channel", "enum:channels", False),
        ("fee_rate_pct", "pct", False),
        ("ad_cost", "won", False),
        ("shipping_cost_per_order", "won", False),
        ("return_handling_cost_per_order", "won", False),
    ],
    # 업로드 필드 이름은 "sales" (주문 CSV 하나 → sales + returns 두 테이블)
    "sales": [
        ("date", "date", True),
        ("product_id", "id", True),
        ("product_name", "str", True),
        ("category", "str", True),
        ("order_id", "id", True),
        ("size", "str", True),
        ("color", "str", True),
        ("is_returned", "bool01", True),
        ("return_type_code", "enum:return_types", True),
        ("return_detail_text", "str", True),
    ],
}

# 다른 파일을 참조하므로 이 순서대로 처리합니다
ORDER = ["products", "suppliers", "purchase_orders", "defects", "costs", "sales"]

# DATA/sample/ 안의 파일 이름
SAMPLE_FILES = {
    "products": "products.csv",
    "suppliers": "suppliers.csv",
    "purchase_orders": "purchase_orders.csv",
    "defects": "defects.csv",
    "costs": "costs.csv",
}
