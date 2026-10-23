# mock 응답 JSON

**소유자:** 태연 · **사용자:** 윤지·예나 (FE)

프론트엔드는 백엔드를 기다리지 않고 이 파일로 개발을 시작합니다.
형식은 [`BE/docs/api.md`](../../../BE/docs/api.md)와 같고, 규약은 [`CONVENTIONS.md`](../../../CONVENTIONS.md)를 따릅니다.

## 파일

| 파일 | 엔드포인트 | 화면 |
|---|---|---|
| `dashboard.json` | `GET /api/dashboard` | 홈 |
| `defect-rates.json` | `GET /api/quality/defect-rates` | 불량률 |
| `inventory.json` | `GET /api/inventory` | 재고·발주 |
| `reorder.json` | `GET /api/inventory/reorder` | 재고·발주 |
| `profit.json` | `GET /api/profit` | 수익성 |
| `returns-rates.json` | `GET /api/returns/rates` | 반품 분석 |
| `returns-analyze.json` | `POST /api/returns/analyze` | 반품 분석 |
| `tasks.json` | `GET`·`POST` `/api/tasks` | 개선 조치 |
| `imports.json` | `POST /api/imports` | 업로드 |
| `errors.json` | — | 오류 처리 UI (엔드포인트 아님) |

## 데이터 출처

| 영역 | 출처 |
|---|---|
| 주문·반품 (`returns-rates`, `returns-analyze`, 재고의 판매 수) | 🟢 **실제** [`datasets/product_return_dataset_2000.csv`](../../../datasets/product_return_dataset_2000.csv)에서 계산 |
| 발주·불량·가격·원가·비용 (`defect-rates`, `reorder`, `profit`) | 🟡 **가정값** — 시환의 추가 CSV 5개가 아직 없음 |

🟢 부분은 그대로 검증 기준으로 쓸 수 있습니다. 🟡 부분은 실제 CSV가 들어오면 **태연이 이 mock을 갱신**합니다.

## 🟡 가정값 — 시환이 CSV를 만들 때 참고

### products.csv

| product_id | product_name | category | price | cost | lead_time_days | moq |
|---|---|---|---|---|---|---|
| P001 | 오버핏 울 코트 | 아우터 | 189000 | 82000 | 21 | 30 |
| P002 | 와이드 데님 팬츠 | 하의/치마 | 59000 | 23000 | 14 | 50 |
| P003 | 패딩 베스트 | 아우터 | 98000 | 41000 | 18 | 30 |
| P004 | 크롭 니트 가디건 | 아우터 | 68000 | 31000 | 14 | 40 |
| P005 | 플리츠 롱스커트 | 하의/치마 | 54000 | 22000 | 12 | 50 |
| P006 | 루즈핏 스웨트셔츠 | 상의/셔츠 | 46000 | 19000 | 10 | 50 |
| **P007** | 심플 로고 맨투맨 | 상의/셔츠 | 42000 | **36000** | 10 | 50 |
| P008 | 기모 후드 집업 | 아우터 | 72000 | 33000 | 14 | 40 |

> P007은 원가율 85.7%로 **기여이익이 음수**가 되도록 설정했습니다 (적자 상품 시연).

### suppliers.csv

`S01` 성수봉제 · `S02` 동대문니트 · `S03` 부산패브릭

### purchase_orders.csv

| po_id | product | supplier | received_at | ordered | received | inspected | defect |
|---|---|---|---|---|---|---|---|
| PO2026-0210-01 | P002 | S01 | 2026-02-10 | 120 | 120 | 120 | 4 |
| PO2026-0618-01 | P002 | S01 | 2026-06-18 | 80 | 80 | 80 | 2 |
| **PO2026-1012-01** | **P002** | **S01** | **2026-10-12** | **50** | **50** | **50** | **4** |
| PO2026-0905-01 | P001 | S02 | 2026-09-05 | 260 | 260 | 260 | 5 |
| PO2026-0820-01 | P003 | S02 | 2026-08-20 | 306 | 306 | 306 | 6 |
| PO2026-0915-01 | P004 | S03 | 2026-09-15 | 236 | 236 | 236 | 6 |
| PO2026-0902-01 | P005 | S03 | 2026-09-02 | 275 | 275 | 275 | 5 |
| PO2026-0825-01 | P006 | S01 | 2026-08-25 | 259 | 259 | 259 | 4 |
| PO2026-0910-01 | P007 | S01 | 2026-09-10 | 274 | 274 | 274 | 4 |
| PO2026-0920-01 | P008 | S02 | 2026-09-20 | 235 | 235 | 235 | 5 |

> **PO2026-1012-01이 급증 건입니다.** 8.0% vs 이전 건 평균 3.0% × 1.5 = 임계 4.5% → 배지 표시.
>
> 🔴 **양품 입고 합계가 주문 수와 맞아야 합니다.** 재고 = 양품 입고 − 주문 수 + 반품 수.
> P002: (120−4) + (80−2) + (50−4) = 240 → 재고 = 240 − 277 + 57 = **20장** → 발주 임박.
> 이 합이 어긋나면 재고가 음수가 되거나 발주 시나리오가 깨집니다.

### defects.csv

| po_id | defect_type | qty |
|---|---|---|
| PO2026-1012-01 | `SEWING` / `FINISH` | 3 / 1 |
| PO2026-0210-01 | `SEWING` / `FINISH` | 3 / 1 |
| PO2026-0618-01 | `SEWING` / `FABRIC` | 1 / 1 |

> P002의 불량을 `SEWING`에 집중시켰습니다. 반품의 `바느질/마감` 5건·`불량 제품` 1건과 **같은 방향**이라 교차 대조 시연이 됩니다.
> 나머지 발주 건은 `defect-rates.json`의 `defect_types`를 참고하세요.

### costs.csv

| 항목 | 값 |
|---|---|
| `fee_rate_pct` | 10.0 (전 상품 공통) |
| `shipping_cost_per_order` | 3000 |
| `return_handling_cost_per_order` | 5000 |
| `ad_cost` (30일) | P001 180000 · P002 250000 · P003 120000 · P004 200000 · P005 90000 · P006 60000 · **P007 비움** · P008 150000 |

> **P007의 `ad_cost`를 비워둡니다.** "일부 비용 미입력"(`MISSING_COST`) 표시 시연용입니다.

### 지표 기본값

`sales_window_days` 7 · `target_cover_days` 14 · `spike_multiplier` 1.5 · `small_sample_threshold` 30 · `overstock_days` 60

## 이 mock에 담긴 시연 포인트

| 포인트 | 어디서 | 값 |
|---|---|---|
| 불량률 **급증 배지** | `defect-rates.json` | PO2026-1012-01 — 8.0%, 임계 4.5% |
| **표본 수 부족** 표시 | `defect-rates.json` | 첫 발주 건은 비교 대상 없음 → `SMALL_SAMPLE` |
| 재고 **발주 시점 경과** | `inventory.json` | P001 — 소진 15.2일 < 리드타임 21일 |
| 재고 **발주 임박** | `inventory.json` | P002 — 발주 필요 시점 0.3일 |
| 재고 **과잉** | `inventory.json` | P003 — 소진 94.3일 |
| **MOQ 올림** | `reorder.json` | P002 필요 20장 → MOQ 50 → **50장** |
| **적자 상품** | `profit.json` | P007 — 기여이익 −21,600원 (−2.9%) |
| **일부 비용 미입력** | `profit.json` | P007 — `missing_costs: ["ad_cost"]` |
| AI **상충 발견** | `returns-analyze.json` | P002 사이즈 의견에 "작다"와 "크다" 공존 |
| **산출 근거** | 전부 | 모든 항목에 `inputs` + `formula` |

## FE가 주의할 것

- 비율은 **이미 0~100**입니다. `_pct` 값에 `× 100`을 하지 마세요.
- `days_to_stockout`·`ad_cost` 등이 `null`일 수 있습니다. `0`으로 표시하지 말고 `notes`의 문구를 쓰세요.
- `formula` 문자열을 **화면에 그대로 출력**하세요. 산출 근거를 보여주는 것이 이 제품의 핵심입니다.
- `cost_breakdown[].share_pct` 합은 반올림 때문에 100.0이 아닐 수 있습니다.
- `returns-analyze.json`은 `AI/fallback/returns-analyze.json`과 내용이 같아도 됩니다 (예나).
