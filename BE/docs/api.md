# API 명세

**소유자:** 태연 · ✅ 전원 합의

- Base URL: `http://localhost:8000`
- 공통 규약: [`CONVENTIONS.md`](../../CONVENTIONS.md) — 키 `snake_case`, 비율 `_pct`(0~100), 금액 정수, ID 문자열
- 열거형: [`DATA/enums.json`](../../DATA/enums.json)
- 지표 공식: [`DATA/metrics.md`](../../DATA/metrics.md)
- **mock: `FE/src/mocks/*.json`** — 프론트엔드는 이 파일로 개발을 시작합니다. 이 명세의 예시 JSON을 그대로 떼내면 됩니다

> 🔴 모든 지표 응답에 `inputs`와 `formula`를 담습니다. 결과값만 반환하면 화면에서 근거를 못 보여줍니다.

---

## 엔드포인트

| Method | Endpoint | mock | 화면 |
|---|---|---|---|
| `POST` | `/api/imports` | `imports.json` | 업로드 |
| `GET` | `/api/dashboard` | `dashboard.json` | 홈 |
| `GET` | `/api/quality/defect-rates` | `defect-rates.json` | 불량률 |
| `GET` | `/api/inventory` | `inventory.json` | 재고·발주 |
| `GET` | `/api/inventory/reorder` | `reorder.json` | 재고·발주 |
| `GET` | `/api/profit` | `profit.json` | 수익성 |
| `GET` | `/api/returns/rates` | `returns-rates.json` | 반품 분석 |
| `POST` | `/api/returns/analyze` | `returns-analyze.json` | 반품 분석 |
| `GET` `POST` | `/api/tasks` | `tasks.json` | 개선 조치 |
| `PATCH` | `/api/tasks/{task_id}` | `tasks.json` | 개선 조치 |

---

## POST /api/imports

`multipart/form-data`. 필드 이름 = 테이블 이름. 여러 파일 동시 업로드 가능.

**200**

```json
{
  "imported": { "products": 8, "suppliers": 3, "purchase_orders": 14, "defects": 22, "sales": 186, "returns": 47, "costs": 8 },
  "warnings": [
    { "file": "defects.csv", "message": "PO2026-0415-02의 불량 유형 합계가 발주 건 불량 수량과 다릅니다" }
  ]
}
```

**400** — 필수 열 누락은 파일 전체 거부

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "업로드 파일에서 2개 행의 오류를 발견했습니다",
    "details": [
      { "file": "purchase_orders.csv", "row": 14, "column": "defect_qty", "value": "-2", "message": "수량은 0 이상의 정수여야 합니다" }
    ]
  }
}
```

---

## GET /api/dashboard

```json
{
  "as_of": "2026-10-24",
  "period": { "from": "2026-09-25", "to": "2026-10-24" },
  "defect": {
    "defect_rate_pct": 4.2,
    "spike_count": 1,
    "worst_supplier": { "supplier_id": "S01", "supplier_name": "성수봉제", "defect_rate_pct": 6.8 }
  },
  "inventory": { "reorder_overdue_count": 1, "reorder_soon_count": 2, "overstock_count": 1 },
  "profit": { "contribution_margin": 1069200, "contribution_margin_pct": 28.0, "negative_product_count": 1 },
  "returns": {
    "return_rate_pct": 9.2,
    "top_reason": { "code": "CHANGE_OF_MIND", "label": "단순 변심", "share_pct": 33.7 },
    "top_actionable_reason": { "code": "SIZE_FIT", "label": "사이즈·핏 문제", "share_pct": 19.6 },
    "worst_product": { "product_id": "P002", "product_name": "와이드 데님 팬츠", "return_rate_pct": 20.6 }
  },
  "notes": []
}
```

---

## GET /api/quality/defect-rates

**쿼리**: `group_by` = `po`(기본) \| `product` \| `supplier` · `product_id` · `supplier_id`

```json
{
  "as_of": "2026-10-24",
  "group_by": "po",
  "items": [
    {
      "po_id": "PO2026-0312-01",
      "product_id": "P001",
      "product_name": "와이드 데님 팬츠",
      "supplier_id": "S01",
      "supplier_name": "성수봉제",
      "received_at": "2026-03-12",
      "received_qty": 200,
      "inspected_qty": 200,
      "defect_qty": 16,
      "good_qty": 184,
      "defect_rate_pct": 8.0,
      "defect_loss_amount": 288000,
      "prior_avg_pct": 2.4,
      "spike_threshold_pct": 3.7,
      "is_spike": true,
      "defect_types": [
        { "code": "SEWING", "label": "봉제·재봉",      "qty": 11, "share_pct": 68.8 },
        { "code": "FABRIC", "label": "원단·소재 결함",  "qty": 3,  "share_pct": 18.8 },
        { "code": "FINISH", "label": "외관·마감",      "qty": 2,  "share_pct": 12.5 }
      ],
      "inputs": { "defect_qty": 16, "inspected_qty": 200, "unit_cost": 18000, "prior_defect_qty": 5, "prior_inspected_qty": 205 },
      "formula": "16 ÷ 200 × 100 = 8.0% · 이전 건 평균 2.4% × 1.5 = 3.7% 초과",
      "notes": []
    }
  ]
}
```

`group_by=supplier`인 경우 `po_id`·`received_at`·`defect_types` 대신 `po_count`를 담습니다.

---

## GET /api/inventory

```json
{
  "as_of": "2026-10-24",
  "sales_window_days": 7,
  "items": [
    {
      "product_id": "P001",
      "product_name": "와이드 데님 팬츠",
      "stock_qty": 40,
      "avg_daily_sales": 6.0,
      "days_to_stockout": 6.7,
      "lead_time_days": 10,
      "reorder_point_days": -3.3,
      "status": "REORDER_OVERDUE",
      "status_label": "발주 시점 경과",
      "inputs": { "cum_good_received": 384, "sold_order_count": 352, "returned_order_count": 8, "sales_window_days": 7, "orders_in_window": 42 },
      "formula": "384 − 352 + 8 = 40장 · 42 ÷ 7 = 6.0장/일 · 40 ÷ 6.0 = 6.7일 · 6.7 − 10 = −3.3일",
      "confidence": "MEDIUM",
      "notes": []
    }
  ]
}
```

산출 불가 예:

```json
{ "avg_daily_sales": null, "days_to_stockout": null, "status": "UNKNOWN",
  "notes": [ { "code": "NOT_COMPUTABLE", "message": "산출 불가" } ] }
```

---

## GET /api/inventory/reorder

**쿼리**: `target_cover_days`(기본 14) · `sales_window_days`(기본 7)

```json
{
  "as_of": "2026-10-24",
  "target_cover_days": 14,
  "items": [
    {
      "product_id": "P001",
      "product_name": "와이드 데님 팬츠",
      "required_qty": 104,
      "defect_adjusted_qty": 110,
      "final_order_qty": 150,
      "inputs": { "avg_daily_sales": 6.0, "lead_time_days": 10, "target_cover_days": 14, "stock_qty": 40, "defect_rate_pct": 5.2, "moq": 50 },
      "formula": "6.0 × (10 + 14) = 144 → − 재고 40 = 104 → ÷ (1 − 0.052) = 109.7 → 올림 110 → MOQ 50 단위 올림 = 150",
      "confidence": "MEDIUM",
      "notes": []
    }
  ]
}
```

> `defect_rate_pct`는 **해당 상품 전체 평균 불량률**입니다. 급증 판정의 `prior_avg_pct`와 다릅니다.

---

## GET /api/profit

**쿼리**: `from` · `to` (기본 최근 30일)

```json
{
  "period": { "from": "2026-09-25", "to": "2026-10-24" },
  "items": [
    {
      "product_id": "P001",
      "product_name": "와이드 데님 팬츠",
      "gross_sales": 4200000,
      "return_amount": 382000,
      "net_sales": 3818000,
      "cost_of_goods": 1584000,
      "platform_fee": 381800,
      "ad_cost": 250000,
      "shipping_cost": 176000,
      "return_handling_cost": 69000,
      "defect_loss": 288000,
      "contribution_margin": 1069200,
      "contribution_margin_pct": 28.0,
      "is_negative": false,
      "cost_breakdown": [
        { "key": "cost_of_goods",        "label": "상품 원가",    "amount": 1584000, "share_pct": 57.6 },
        { "key": "platform_fee",         "label": "플랫폼 수수료", "amount": 381800,  "share_pct": 13.9 },
        { "key": "defect_loss",          "label": "불량 손실",    "amount": 288000,  "share_pct": 10.5 },
        { "key": "ad_cost",              "label": "광고비",       "amount": 250000,  "share_pct": 9.1 },
        { "key": "shipping_cost",        "label": "배송비",       "amount": 176000,  "share_pct": 6.4 },
        { "key": "return_handling_cost", "label": "반품 처리비",   "amount": 69000,   "share_pct": 2.5 }
      ],
      "missing_costs": [],
      "inputs": { "sold_order_count": 88, "returned_order_count": 8, "unit_cost": 18000, "price": 48000, "fee_rate_pct": 10.0, "defect_qty": 16 },
      "formula": "3,818,000 − 1,584,000 − 381,800 − 495,000 − 288,000 = 1,069,200원 (28.0%)",
      "notes": []
    }
  ]
}
```

비용 누락 예:

```json
{ "ad_cost": null, "missing_costs": ["ad_cost"],
  "notes": [ { "code": "MISSING_COST", "message": "일부 비용 미입력" } ] }
```

---

## GET /api/returns/rates

```json
{
  "period": { "from": "2026-09-25", "to": "2026-10-24" },
  "items": [
    {
      "product_id": "P002",
      "product_name": "와이드 데님 팬츠",
      "order_count": 277,
      "return_count": 57,
      "return_rate_pct": 20.6,
      "basis": "count",
      "reasons": [
        { "code": "SIZE_FIT",       "label": "사이즈·핏 문제",   "count": 22, "share_pct": 38.6 },
        { "code": "CHANGE_OF_MIND", "label": "단순 변심",       "count": 18, "share_pct": 31.6 },
        { "code": "QUALITY_FINISH", "label": "봉제·마감 불만",   "count": 5,  "share_pct": 8.8 },
        { "code": "COLOR_IMAGE",    "label": "색상·이미지 차이", "count": 5,  "share_pct": 8.8 },
        { "code": "SHIPPING",       "label": "배송·포장",       "count": 3,  "share_pct": 5.3 },
        { "code": "OTHER",          "label": "기타·판단 불확실", "count": 2,  "share_pct": 3.5 },
        { "code": "FABRIC_FEEL",    "label": "원단·촉감·두께",   "count": 1,  "share_pct": 1.8 },
        { "code": "DEFECTIVE",      "label": "불량 제품",       "count": 1,  "share_pct": 1.8 }
      ],
      "inputs": { "order_count": 277, "return_count": 57 },
      "formula": "57 ÷ 277 × 100 = 20.6%",
      "notes": []
    }
  ]
}
```

> 주문 단위 데이터이므로 **전부 건수 기준**입니다 (`basis: "count"`). 주문 1건 = 1장으로 간주합니다.
> 위 수치는 `datasets/product_return_dataset_2000.csv`의 **실제 P002 값**입니다. 그대로 검증에 쓸 수 있습니다.

---

## POST /api/returns/analyze

**요청**

```json
{ "product_id": "P001", "period": { "from": "2026-09-25", "to": "2026-10-24" } }
```

**200** — 응답 구조는 [`AI/README.md`](../../AI/README.md)와 `AI/schemas/return-analysis.schema.json`에 정의됩니다.

> 🔴 **LLM 호출이 실패해도 200으로 폴백 응답을 반환합니다** (`"fallback": true`). `AI/fallback/returns-analyze.json`을 그대로 반환하세요. 에러를 반환하면 시연이 멈춥니다.

---

## 개선 조치

### POST /api/tasks

```json
{
  "product_id": "P001",
  "title": "허벅지 둘레 실측표 재확인",
  "type": "PRODUCT_FIX",
  "assignee": "시환",
  "due_date": "2026-10-28",
  "source": { "type": "RETURN_ANALYSIS", "ref": "P001" }
}
```

**201**

```json
{
  "task_id": "T0003",
  "product_id": "P001",
  "product_name": "와이드 데님 팬츠",
  "title": "허벅지 둘레 실측표 재확인",
  "type": "PRODUCT_FIX",
  "type_label": "실제 상품 수정",
  "assignee": "시환",
  "due_date": "2026-10-28",
  "status": "PENDING",
  "status_label": "대기",
  "created_at": "2026-10-24",
  "source": { "type": "RETURN_ANALYSIS", "ref": "P001" }
}
```

### PATCH /api/tasks/{task_id}

```json
{ "status": "IN_PROGRESS" }
```

변경 가능: `status` · `assignee` · `due_date` · `title`. 응답은 갱신된 task 객체.

### GET /api/tasks

**쿼리**: `product_id` · `status` → `{ "items": [ /* task 배열 */ ] }`

---

## 에러

| HTTP | code | 상황 |
|---|---|---|
| 400 | `VALIDATION_FAILED` | 파라미터 또는 CSV 오류 |
| 404 | `NOT_FOUND` | ID 없음 |
| 422 | `NOT_COMPUTABLE` | 데이터 부족으로 계산 불가 |
| 500 | `INTERNAL_ERROR` | 그 외 |

형식은 [`CONVENTIONS.md §10`](../../CONVENTIONS.md)을 따릅니다. LLM 실패는 에러가 아니라 폴백 + 200입니다.
