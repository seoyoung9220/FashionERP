# 데이터 사전

**소유자:** 시환 · 마감 **0:30** 🔴 크리티컬 패스 · 샘플: `sample/*.csv`

CSV는 **UTF-8**, 첫 행은 헤더, 열 이름은 아래와 **정확히 일치**해야 합니다.
열 이름 매핑 UI를 만들지 않으므로 **이 이름이 곧 계약**입니다.

공통: 날짜 `YYYY-MM-DD` · 금액 정수(원) · 비율 0~100 · ID 문자열 · 불리언 `TRUE`/`FALSE` · 열거형은 [`enums.json`](./enums.json)

---

## products.csv — 상품

| 열 | 자료형 | 필수 | 단위 | 설명 |
|---|---|---|---|---|
| `product_id` | 문자열 | ✅ | — | `P001` 형식. 전체 데이터의 연결 기준 |
| `product_name` | 문자열 | ✅ | — | 상품명 |
| `category` | 문자열 | | — | 팬츠 / 니트 / 셔츠 등 |
| `price` | 정수 | ✅ | 원 | 판매가 |
| `cost` | 정수 | ✅ | 원 | 상품 원가 |
| `lead_time_days` | 정수 | ✅ | 일 | 발주 후 입고까지 소요일 |
| `moq` | 정수 | ✅ | 장 | 최소 발주 수량 |

## suppliers.csv — 거래처

| 열 | 자료형 | 필수 | 설명 |
|---|---|---|---|
| `supplier_id` | 문자열 | ✅ | `S01` 형식 |
| `supplier_name` | 문자열 | ✅ | 거래처명 |

## purchase_orders.csv — 발주 · 입고 검수

| 열 | 자료형 | 필수 | 단위 | 설명 |
|---|---|---|---|---|
| `po_id` | 문자열 | ✅ | — | `PO2026-0312-01` 형식 |
| `product_id` | 문자열 | ✅ | — | products 참조 |
| `supplier_id` | 문자열 | ✅ | — | suppliers 참조 |
| `ordered_at` | 날짜 | ✅ | — | 발주일 |
| `received_at` | 날짜 | | — | 입고일. 미입고면 비움 |
| `ordered_qty` | 정수 | ✅ | 장 | 발주 수량 |
| `received_qty` | 정수 | | 장 | 입고 수량 |
| `inspected_qty` | 정수 | | 장 | **검수 수량 — 불량률의 분모** |
| `defect_qty` | 정수 | | 장 | 불량 수량 |

> 🔴 `inspected_qty`가 불량률의 분모입니다. 전수 검수가 아니면 `received_qty`와 다를 수 있고, 그때는 표본 수로 함께 표시합니다.
> `defect_qty` ≤ `inspected_qty` ≤ `received_qty` ≤ `ordered_qty` 관계를 검증합니다.

## defects.csv — 불량 유형별 수량

| 열 | 자료형 | 필수 | 단위 | 설명 |
|---|---|---|---|---|
| `po_id` | 문자열 | ✅ | — | purchase_orders 참조 |
| `defect_type` | 열거형 | ✅ | — | `defect_types` 코드 |
| `defect_qty` | 정수 | ✅ | 장 | 해당 유형 수량 |

> 같은 `po_id`의 `defect_qty` 합계 = `purchase_orders.defect_qty` 여야 합니다.

## sales.csv — 판매

| 열 | 자료형 | 필수 | 단위 | 설명 |
|---|---|---|---|---|
| `sold_at` | 날짜 | ✅ | — | 판매일 |
| `product_id` | 문자열 | ✅ | — | products 참조 |
| `channel` | 열거형 | ✅ | — | `sales_channels` 코드 |
| `sold_qty` | 정수 | ✅ | 장 | 판매 수량 |
| `sales_amount` | 정수 | ✅ | 원 | 실제 판매 금액 |

> 일자별·채널별로 한 행씩. 집계 단위는 **1일**로 통일합니다.

## returns.csv — 반품

| 열 | 자료형 | 필수 | 단위 | 설명 |
|---|---|---|---|---|
| `return_id` | 문자열 | ✅ | — | `R0012` 형식 |
| `returned_at` | 날짜 | ✅ | — | 반품일 |
| `product_id` | 문자열 | ✅ | — | products 참조 |
| `return_qty` | 정수 | ✅ | 장 | 반품 수량 |
| `reason_code` | 열거형 | | — | 고객이 **선택한** 사유. `return_reasons` 코드. 비워도 됨 |
| `review_text` | 문자열 | | — | 고객이 **작성한** 자유 서술. **AI 분석 입력** |
| `resellable` | 불리언 | ✅ | — | `TRUE`/`FALSE`. 재판매 가능 여부 → 재고 복귀 판단 |

> `reason_code`와 `review_text`는 다릅니다. AI는 `review_text`를 분류하고, `reason_code`는 비교 대조용입니다.

## costs.csv — 비용

| 열 | 자료형 | 필수 | 단위 | 설명 |
|---|---|---|---|---|
| `product_id` | 문자열 | ✅ | — | products 참조. `*`면 전체 공통 |
| `channel` | 열거형 | | — | 비우면 전체 채널 공통 |
| `fee_rate_pct` | 숫자 | | % | 플랫폼 수수료율. 0~100 |
| `ad_cost` | 정수 | | 원 | 기간 내 광고비 총액 |
| `shipping_cost_per_order` | 정수 | | 원 | 건당 배송비 |
| `return_handling_cost_per_order` | 정수 | | 원 | 건당 반품 처리비 |

> 비어 있는 비용 항목은 계산에서 제외하고 `notes`에 `MISSING_COST`를 담습니다. **0으로 채우지 않습니다.**

---

## 업로드 검증 규칙

| # | 규칙 | 위반 시 |
|---|---|---|
| 1 | 필수 열이 전부 존재 | 400 `VALIDATION_FAILED` — 파일 전체 거부 |
| 2 | 필수 값이 비어 있지 않음 | 해당 행 오류 보고, 나머지 적재 |
| 3 | 수량·금액이 0 이상 정수 | 해당 행 오류 보고 |
| 4 | 비율이 0~100 | 해당 행 오류 보고 |
| 5 | 날짜가 `YYYY-MM-DD` | 해당 행 오류 보고 |
| 6 | 열거형 값이 `enums.json`에 존재 | 해당 행 오류 보고 |
| 7 | 참조 ID가 실제로 존재 | 해당 행 오류 보고 |
| 8 | `defect_qty` ≤ `inspected_qty` ≤ `received_qty` ≤ `ordered_qty` | 해당 행 오류 보고 |
| 9 | `defects.csv` 합계 = `purchase_orders.defect_qty` | 경고 (적재는 진행) |
| 10 | `po_id`·`return_id` 중복 없음 | 해당 행 오류 보고 |

오류 응답 형식은 [`CONVENTIONS.md §10`](../CONVENTIONS.md)을 따릅니다.
