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
| `POST` | `/api/sales` | `sales-create.json` | 홈 · 새 주문 입력 [계약변경] |
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

**쿼리**: `from` · `to` (YYYY-MM-DD) · `product_id` — **생략하면 전체 데이터 기간**(첫 주문일 ~ 마지막 주문일)으로 계산합니다.
기간을 주면 그 기간의 주문일 기준으로 계산합니다. (수익성 `/api/profit`의 기본은 최근 30일로 다릅니다)

```json
{
  "period": { "from": "2026-01-10", "to": "2026-10-24" },
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

## GET /api/returns/review-keywords

반품 리뷰 문장(`return_detail_text`)을 **규칙 기반 키워드 사전**으로 분류합니다. AI 호출이 없어 같은 입력이면 항상 같은 결과입니다.
코드: `BE/app/services/review_keywords.py` · 테스트: `BE/test_review_keywords.py` · mock: `FE/src/mocks/review-keywords.json`

**쿼리**: `from` · `to` · `product_id` — 생략하면 **전체 데이터 기간** (`/api/returns/rates`와 같은 기준)

| 분류 코드 | 라벨 | 대표 키워드 (실제 리뷰 표현) |
|---|---|---|
| `SIZE_FIT` | 사이즈·핏 | 사이즈 · 작게 · 품이 · 기장 · 타이트 · 허리 · 골반 |
| `QUALITY` | 품질·마감 | 마감 · 실밥 · 올이 풀 · 오염 · 지퍼 · 뻑뻑 |
| `FABRIC` | 소재·원단 | 원단 · 얇아 · 소재 · 까끌 |
| `COLOR` | 색상·이미지 차이 | 색감 · 사진과 · 화면보다 · 어두운 |
| `DESIGN` | 디자인·실물 느낌 | 실물 · 느낌이 아니 |
| `SHIPPING` | 배송·포장 | 배송 · 늦어 · 박스 · 찌그러 · 패키지 · 손상 |
| `CHANGE_OF_MIND` | 단순 변심·개인 사정 | 선물 · 일정 · 다른 색상 · 더 나을 것 같 |
| `UNCLASSIFIED` | 분류 불가 | 키워드 없음 또는 "기타 사유로 …"처럼 원인을 말하지 않는 문장 |

> **집계 기준** — 한 리뷰에 여러 분류 키워드가 있으면 **각 분류에 1건씩** 셉니다 (`multi_label_count`).
> `share_pct = 분류별 리뷰 수 ÷ analyzed_count × 100` 이므로 **합계가 100%를 넘을 수 있습니다.**
> `reason_code_cross`는 고객이 고른 반품 사유(`return_type_code`)와 문장 분류의 교차 건수입니다.
> 이 분류 코드는 화면 표시용 별도 체계이며 `enums.json`의 `return_reasons`와 다릅니다. ([계약변경] 신규 API)

```json
{
  "period": {
    "from": "2026-01-10",
    "to": "2026-10-24"
  },
  "product_id": null,
  "return_count": 184,
  "basis": "review",
  "analyzed_count": 184,
  "unique_text_count": 17,
  "classified_count": 179,
  "unclassified_count": 5,
  "multi_label_count": 0,
  "categories": [
    {
      "code": "QUALITY",
      "label": "품질·마감",
      "count": 44,
      "share_pct": 23.9,
      "keywords": [
        {
          "keyword": "마감",
          "count": 22
        },
        {
          "keyword": "지퍼",
          "count": 17
        }
      ],
      "example": {
        "order_id": "P008-20260628-0006",
        "product_id": "P008",
        "text": "지퍼 윗부분이 뻑뻑해서 잘 잠기지 않습니다"
      }
    },
    {
      "code": "CHANGE_OF_MIND",
      "label": "단순 변심·개인 사정",
      "count": 40,
      "share_pct": 21.7,
      "keywords": [
        {
          "keyword": "선물",
          "count": 22
        },
        {
          "keyword": "일정",
          "count": 22
        }
      ],
      "example": {
        "order_id": "P002-20261005-0082",
        "product_id": "P002",
        "text": "선물하려고 했는데 일정이 취소되었어요"
      }
    },
    {
      "…": "8개 분류 중 2개만 표시"
    }
  ],
  "top_keywords": [
    {
      "keyword": "선물",
      "category": "CHANGE_OF_MIND",
      "category_label": "단순 변심·개인 사정",
      "count": 22,
      "share_pct": 12.0
    },
    {
      "keyword": "일정",
      "category": "CHANGE_OF_MIND",
      "category_label": "단순 변심·개인 사정",
      "count": 22,
      "share_pct": 12.0
    }
  ],
  "sample_review": {
    "order_id": "P008-20260628-0006",
    "product_id": "P008",
    "text": "지퍼 윗부분이 뻑뻑해서 잘 잠기지 않습니다",
    "matches": [
      {
        "keyword": "지퍼",
        "category": "QUALITY",
        "category_label": "품질·마감"
      },
      {
        "keyword": "뻑뻑",
        "category": "QUALITY",
        "category_label": "품질·마감"
      },
      {
        "keyword": "잠기지 않",
        "category": "QUALITY",
        "category_label": "품질·마감"
      }
    ]
  },
  "reason_code_cross": [
    {
      "reason_code": "CHANGE_OF_MIND",
      "category": "CHANGE_OF_MIND",
      "count": 40
    },
    {
      "reason_code": "SIZE_FIT",
      "category": "SIZE_FIT",
      "count": 36
    }
  ],
  "inputs": {
    "analyzed_count": 184,
    "classified_count": 179
  },
  "formula": "분류 비율 = 분류별 리뷰 수 ÷ 분석 리뷰 수 × 100 (한 리뷰가 여러 분류면 각각 1건, 합계 100% 초과 가능)",
  "notes": [
    {
      "code": "LOW_CONFIDENCE",
      "message": "서로 다른 리뷰 문장이 17종뿐이라 같은 문장이 반복됩니다. 키워드 다양성이 낮습니다"
    }
  ]
}
```

---

## 추이·구성 API (홈 매출 흐름 · 판매 비교 · 재고자산 · 월별 수익 · 카테고리 비중)

코드: `BE/app/services/trends.py` · 테스트: `BE/test_trends.py` · mock: `FE/src/mocks/sales-daily.json` 등 5개 ([계약변경] 신규 API)
🔴 새 공식 없음 — 금액은 `metrics.md` §3, 재고는 §2 를 그대로 씁니다. 월별·카테고리 기여이익은 기존 `/api/profit` 계산(`profit_query.profit`)을 기간·상품별로 불러 더합니다.

| 경로 | 쿼리 (기본) | 화면 |
|---|---|---|
| `GET /api/sales/daily` | `from`·`to` (최근 7일) | 홈 · 매출 흐름 |
| `GET /api/sales/momentum` | `window_days` (7) | 재고 · 판매 급증 카드 (참고값) |
| `GET /api/inventory/value` | — | 재고 · 전체 재고자산 |
| `GET /api/profit/monthly` | `from`·`to` (전체 데이터 기간) | 수익 · 매출·추정 기여이익 추이 |
| `GET /api/profit/categories` | `from`·`to` (최근 30일, `/api/profit`과 같음) | 수익 · 카테고리별 매출 비중 |

> - **판매 급증**: `metrics.md`에 정의가 없어 **판정하지 않습니다** (`is_surge: null`, `rule_defined: false`). 최근 N일 vs 직전 N일 주문 수와 증가율만 주고, `suggested_rule`에 제안 기준을 담습니다.
> - **월별 기여이익**: 광고비(`ad_cost`)는 기간 전체에 한 번 드는 금액이고 월 배분 규칙이 없어, 월별 값은 `contribution_margin_excl_ad`(광고비 제외)로 주고 `total`에서 한 번만 뺍니다. → `total.contribution_margin` = 같은 기간 `/api/profit` 기여이익 합.
> - **불량 손실**은 `metrics.md` §3 대로 **입고일(received_at)이 그 달**인 발주 건 기준입니다.
> - **카테고리 비중** = 카테고리 순매출 ÷ 전체 순매출 × 100. 총매출 기준 비중은 `gross_share_pct`. `total.check_sum_net_sales`로 합계 일치를 확인합니다.
> - **재고자산** = Σ(현재 재고 × `products.cost`). 원가 기준 평가, 반품 전량 재고 복귀 가정.

### GET /api/sales/daily
```json
{
  "period": {
    "from": "2026-10-18",
    "to": "2026-10-24"
  },
  "basis": "order_date",
  "total": {
    "order_count": 58,
    "gross_sales": 5533000,
    "net_sales": 4894000
  },
  "items": [
    {
      "date": "2026-10-18",
      "order_count": 9,
      "return_count": 1,
      "gross_sales": 1029000,
      "return_amount": 189000,
      "net_sales": 840000,
      "inputs": {
        "order_count": 9,
        "return_count": 1
      },
      "formula": "총매출 1,029,000 − 반품 189,000 = 순매출 840,000원",
      "notes": []
    }
  ],
  "formula": "일별 순매출 = Σ(그날 주문 × 판매가) − Σ(그날 주문 중 반품 × 판매가)",
  "notes": [],
  "_items_note": "items 7개 중 1개만 표시"
}
```
### GET /api/sales/momentum
```json
{
  "as_of": "2026-10-24",
  "window_days": 7,
  "basis": "order_count",
  "current_period": {
    "from": "2026-10-18",
    "to": "2026-10-24"
  },
  "previous_period": {
    "from": "2026-10-11",
    "to": "2026-10-17"
  },
  "rule_defined": false,
  "suggested_rule": "제안(미적용): 최근 7일 주문 ≥ 직전 7일 주문 × 1.5 이고 직전 7일 주문 ≥ 5건 — 불량률 급증과 같은 1.5배 기준. metrics.md 에 판매 급증 정의가 없어 팀 합의 전에는 판정하지 않습니다",
  "items": [
    {
      "product_id": "P001",
      "product_name": "오버핏 울 코트",
      "category": "아우터",
      "current_orders": 15,
      "previous_orders": 4,
      "change": 11,
      "change_pct": 275.0,
      "is_surge": null,
      "inputs": {
        "current_period": {
          "from": "2026-10-18",
          "to": "2026-10-24"
        },
        "previous_period": {
          "from": "2026-10-11",
          "to": "2026-10-17"
        }
      },
      "formula": "(15 − 4) ÷ 4 × 100 = 275.0%",
      "notes": []
    }
  ],
  "notes": [
    {
      "code": null,
      "message": "판매 급증 기준이 metrics.md 에 없어 증가율만 제공하고 급증 여부는 판정하지 않습니다"
    }
  ],
  "_items_note": "items 8개 중 1개만 표시"
}
```
### GET /api/inventory/value
```json
{
  "as_of": "2026-10-24",
  "basis": "cost",
  "total_qty": 234,
  "total_value": 9160000,
  "excluded": [],
  "items": [
    {
      "product_id": "P001",
      "product_name": "오버핏 울 코트",
      "stock_qty": 32,
      "unit_cost": 82000,
      "stock_value": 2624000,
      "inputs": {
        "stock_qty": 32,
        "unit_cost": 82000
      },
      "formula": "32장 × 82,000원 = 2,624,000원",
      "notes": []
    }
  ],
  "inputs": {
    "product_count": 8,
    "valued_product_count": 8
  },
  "formula": "Σ(상품별 현재 재고 × 원가) = 9,160,000원 · 재고 234장",
  "notes": [
    {
      "code": null,
      "message": "원가(products.cost) 기준 평가 · 반품은 전량 재고 복귀 가정 (metrics.md §2)"
    }
  ],
  "_items_note": "items 8개 중 1개만 표시"
}
```
### GET /api/profit/monthly
```json
{
  "period": {
    "from": "2026-01-10",
    "to": "2026-10-24"
  },
  "items": [
    {
      "gross_sales": 12538000,
      "return_amount": 1156000,
      "net_sales": 11382000,
      "cost_of_goods": 5227000,
      "platform_fee": 1138200,
      "shipping_cost": 480000,
      "return_handling_cost": 70000,
      "defect_loss": 0,
      "month": "2026-01",
      "from": "2026-01-10",
      "to": "2026-01-31",
      "partial": true,
      "order_count": 160,
      "return_count": 14,
      "contribution_margin_excl_ad": 4466800,
      "contribution_margin_excl_ad_pct": 39.2,
      "inputs": {
        "order_count": 160,
        "return_count": 14,
        "net_sales": 11382000,
        "cost_of_goods": 5227000,
        "platform_fee": 1138200,
        "shipping_cost": 480000,
        "return_handling_cost": 70000,
        "defect_loss": 0
      },
      "formula": "11,382,000 − 5,227,000 − 1,138,200 − 550,000 − 0 = 4,466,800원 (광고비 제외)",
      "notes": []
    }
  ],
  "total": {
    "gross_sales": 154308000,
    "net_sales": 140975000,
    "contribution_margin_excl_ad": 53595500,
    "ad_cost": 1050000,
    "contribution_margin": 52545500,
    "contribution_margin_pct": 37.3,
    "missing_costs": [
      "ad_cost"
    ]
  },
  "formula": "Σ 월별(광고비 제외) 53,595,500 − 광고비 1,050,000 = 추정 기여이익 52,545,500원",
  "notes": [
    {
      "code": null,
      "message": "광고비(ad_cost)는 월 배분 규칙이 없어 월별 값에서 제외하고 합계에서 한 번만 뺐습니다"
    },
    {
      "code": "MISSING_COST",
      "message": "일부 비용 미입력"
    },
    {
      "code": null,
      "message": "처음·마지막 달은 데이터가 있는 날짜까지만 집계했습니다 (partial: true)"
    }
  ],
  "_items_note": "items 10개 중 1개만 표시"
}
```
### GET /api/profit/categories
```json
{
  "period": {
    "from": "2026-09-25",
    "to": "2026-10-24"
  },
  "basis": "net_sales",
  "total": {
    "net_sales": 15485000,
    "gross_sales": 17364000,
    "category_count": 3,
    "check_sum_net_sales": true
  },
  "items": [
    {
      "category": "아우터",
      "product_count": 4,
      "product_ids": [
        "P001",
        "P003",
        "P004",
        "P008"
      ],
      "order_count": 114,
      "gross_sales": 12716000,
      "net_sales": 11427000,
      "share_pct": 73.8,
      "gross_share_pct": 73.2,
      "contribution_margin": 4221300,
      "contribution_margin_pct": 36.9,
      "missing_costs": [],
      "inputs": {
        "net_sales": 11427000,
        "total_net_sales": 15485000
      },
      "formula": "11,427,000 ÷ 15,485,000 × 100 = 73.8%",
      "notes": []
    }
  ],
  "formula": "카테고리 비중 = 카테고리 순매출 ÷ 전체 순매출 × 100 (순매출 = 총매출 − 반품 금액, metrics.md §3)",
  "notes": [],
  "_items_note": "items 3개 중 1개만 표시"
}
```

---

## POST /api/sales — 새 주문 1건 입력 [계약변경]

홈 하단 '새 주문 입력' 칸이 부릅니다. 코드: `BE/app/services/order_input.py` · 테스트: `BE/test_order_input.py` · mock: `FE/src/mocks/sales-create.json`

- 주문 CSV 한 행과 같은 항목을 JSON 으로 받습니다. 검증은 `/api/imports` 와 **같은 규칙**(`importers/loader.py`)입니다.
- `/api/imports` 는 표를 통째로 교체하지만, 이 API 는 **1건만 추가**합니다.
- `order_id` 는 `{product_id}-{YYYYMMDD}-{일련번호}` 로 자동 생성, `product_name`·`category` 는 products 에서 채웁니다. 1주문 = 1장.
- 반품이면 returns 에 1행 추가(`return_id` 자동). 반품 유형은 영문 코드 또는 한글 라벨 모두 받고 코드로 저장합니다.
- 반품인데 유형이 비어 있으면 `return_type_code: null` 로 저장하고 `warnings` 에 담습니다 (규칙 11, 0 아님).
- 🔴 **날짜**: 기준일(as_of) = 주문 데이터의 마지막 날짜이므로, **오늘(KST) 이후 날짜는 400 `VALIDATION_FAILED`(column `date`)** 로 거절합니다. 기준일보다 나중 날짜(오늘 이하)는 저장하되 `warnings` 에 "데이터 기준일이 A → B 로 바뀌어…"를 담습니다. 화면은 주문일 기본값을 오늘이 아니라 기준일로 채웁니다.

요청
```json
{ "date": "2026-10-24", "product_id": "P007", "size": "L", "color": "Gray",
  "is_returned": true, "return_type_code": "SIZE_FIT", "return_detail_text": "생각보다 작아요" }
```

**201**
```json
{ "order": { "order_id": "P007-20261024-0001", "date": "2026-10-24", "product_id": "P007", "product_name": "심플 로고 맨투맨",
             "category": "상의/셔츠", "size": "L", "color": "Gray", "qty": 1, "is_returned": 1,
             "return_type_code": "SIZE_FIT", "return_detail_text": "생각보다 작아요" },
  "return_id": "R0185", "warnings": [] }
```

**400** — 아무것도 저장하지 않음 (`details` 형식은 `/api/imports` 와 같음, `file` = "입력 폼")

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
