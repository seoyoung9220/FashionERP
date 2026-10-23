# AI — 반품 원인 분석

**담당:** 서영 (분석·프롬프트·스키마) · 예나 (검증·폴백·테스트)

🔴 **AI는 반품 원인 분석 한 곳에만 씁니다.** 불량률·재고·수익성은 공식 계산입니다 ([`DATA/metrics.md`](../DATA/metrics.md)).

## 폴더

```
AI/
├── prompts/     return-analysis.md          ← 서영 ✅ 작성됨
├── schemas/     return-analysis.schema.json ← 서영 ✅ 작성됨
├── fallback/    returns-analyze.json        ← 예나 🔴 최우선
└── tests/       cases.md                    ← 예나
```

## 분석 대상 데이터

[`datasets/product_return_dataset_2000.csv`](../datasets/product_return_dataset_2000.csv) — 주문 2,000건 중 **반품 184건**

| 항목 | 값 |
|---|---|
| 자유 서술 | `return_detail_text` 184건 (홑따옴표로 감싸져 있음 → 적재 시 제거) |
| 고객 선택 사유 | `return_type_code` 한글 라벨 8종 |
| 차원 | `size`(M/L/XL) · `color`(8종) → 사이즈·색상별 집중도 분석 가능 |
| **시연 주인공** | **P002 와이드 데님 팬츠 — 반품 57/277 = 20.6%** (전체 평균 9.2%) |

> 이 데이터는 이미 저장소에 있습니다. **시환의 추가 CSV를 기다리지 않고 바로 시작할 수 있습니다.**

## 입력 (백엔드 → LLM)

백엔드가 DB에서 모아 프롬프트에 넣습니다. **원본 CSV를 그대로 넣지 않습니다.**

| 필드 | 용도 |
|---|---|
| `product`, `period`, `stats` | 맥락 (상품명, 기간, 주문 수, 반품 수, 반품률) |
| `returns[]` | **분류 대상.** `order_id` + `return_detail_text` |
| `selected_reasons[]` | 고객이 **선택한** `return_type_code`. 분류 결과와 대조용 — 분류 입력이 아님 |
| `dimension_counts` | 반품 건의 `size`·`color` 분포 — 특정 사이즈·색상 집중 여부 확인용 |
| `defect_context[]` | 입고 검수 불량 유형. `DEFECTIVE`·`QUALITY_FINISH` 반품과 방향이 같은지 확인용. 시환의 `defects.csv`가 나오기 전엔 비어 있음 |

> `returns`가 비어 있으면 LLM을 호출하지 않고 `insufficient_data: true`를 즉시 반환합니다.

## 출력 — 네 블록을 반드시 분리

스키마: [`schemas/return-analysis.schema.json`](./schemas/return-analysis.schema.json)
관측된 사실과 AI 추정을 섞으면 안 됩니다.

| 블록 | 필드 | 성격 |
|---|---|---|
| 관측된 사실 | `observed_facts` | 데이터에서 직접 확인되는 수치. **근거 원문 필수** |
| 가능한 원인 | `possible_causes` | 단정하지 않는 후보. `confidence` 필수 |
| 추가 확인 사항 | `checks_needed` | 사용자가 직접 확인할 것 |
| 개선 체크리스트 | `improvement_checklist` | 등록 가능한 작업. `PAGE_FIX` / `PRODUCT_FIX` 구분 |

선택 필드 — `size_color_findings`(사이즈·색상 집중도), `cross_check`(입고 불량과의 대조).

아래는 **실제 데이터셋의 P002 값**으로 채운 예시입니다. 인용문과 `order_id`도 실제 행에서 가져왔습니다.

```json
{
  "product_id": "P002",
  "period": { "from": "2026-01-10", "to": "2026-10-24" },
  "analyzed_count": 57,
  "categories": [
    { "code": "SIZE_FIT",       "label": "사이즈·핏 문제",   "count": 22, "share_pct": 38.6 },
    { "code": "CHANGE_OF_MIND", "label": "단순 변심",       "count": 18, "share_pct": 31.6 },
    { "code": "QUALITY_FINISH", "label": "봉제·마감 불만",   "count": 5,  "share_pct": 8.8 },
    { "code": "COLOR_IMAGE",    "label": "색상·이미지 차이", "count": 5,  "share_pct": 8.8 },
    { "code": "SHIPPING",       "label": "배송·포장",       "count": 3,  "share_pct": 5.3 },
    { "code": "OTHER",          "label": "기타·판단 불확실", "count": 2,  "share_pct": 3.5 },
    { "code": "FABRIC_FEEL",    "label": "원단·촉감·두께",   "count": 1,  "share_pct": 1.8 },
    { "code": "DEFECTIVE",      "label": "불량 제품",       "count": 1,  "share_pct": 1.8 }
  ],
  "observed_facts": [
    {
      "statement": "반품 57건 중 22건(38.6%)이 사이즈·핏 문제로, 단일 범주 중 가장 큽니다",
      "evidence_quotes": [
        "사이즈가 작게 나와서 한 사이즈 큰 걸로 다시 사야겠어요",
        "평소 M을 입는데 골반과 허리가 너무 타이트합니다"
      ],
      "evidence_order_ids": ["P002-20260908-0009", "P002-20260421-0426"]
    },
    {
      "statement": "사이즈·핏 의견 안에 \"작다\"와 \"품이 크다\"가 함께 나타납니다",
      "evidence_quotes": [
        "사이즈가 작게 나와서 한 사이즈 큰 걸로 다시 사야겠어요",
        "생각보다 품이 너무 크고 기장도 어정쩡해요"
      ],
      "evidence_order_ids": ["P002-20260908-0009", "P002-20260626-0099"]
    }
  ],
  "possible_causes": [
    {
      "statement": "부위별 치수가 고객 기대와 다를 가능성 — 허리·골반은 타이트하고 품·기장은 크다는 의견이 공존합니다",
      "confidence": "MEDIUM",
      "related_categories": ["SIZE_FIT"]
    },
    {
      "statement": "상품 페이지의 사이즈 안내가 부위별 실측을 충분히 제공하지 않을 가능성",
      "confidence": "MEDIUM",
      "related_categories": ["SIZE_FIT"]
    }
  ],
  "checks_needed": [
    "사이즈별 허리·골반·품·기장 실측 치수 확인",
    "상품 페이지에 안내된 사이즈 표와 실측값 대조",
    "특정 사이즈에 반품이 쏠리는지 확인 — L 38.6% / M 35.1% / XL 26.3% 로 비교적 고르게 분포"
  ],
  "improvement_checklist": [
    { "title": "상품 페이지에 부위별 실측 치수 추가 (허리·골반·품·기장)", "type": "PAGE_FIX",    "rationale": "안내 부족으로 인한 반품이면 페이지 수정만으로 줄일 수 있습니다" },
    { "title": "다음 샘플 제작 전 허리·골반 대비 품 비율 검토",          "type": "PRODUCT_FIX", "rationale": "타이트하다는 의견과 품이 크다는 의견이 공존해 패턴 비율 확인이 필요합니다" }
  ],
  "size_color_findings": [
    { "dimension": "size", "value": "L",  "count": 22, "share_pct": 38.6 },
    { "dimension": "size", "value": "M",  "count": 20, "share_pct": 35.1 },
    { "dimension": "size", "value": "XL", "count": 15, "share_pct": 26.3 }
  ],
  "insufficient_data": false,
  "fallback": false,
  "notes": []
}
```

> `categories`의 분포는 데이터셋의 `return_type_code`(고객이 선택한 사유)를 집계한 값입니다.
> AI가 `return_detail_text`를 분류한 결과는 이와 **다를 수 있습니다** — 그 차이가 바로 `selected_reasons`와 대조할 지점입니다.
> `size_color_findings`가 고르게 분포하면 "특정 사이즈 집중 없음"으로 보고하고 원인을 사이즈 편차로 단정하지 않습니다.

분류 코드는 [`DATA/enums.json`](../DATA/enums.json)의 `return_reasons` **8종**만 씁니다.
데이터셋의 한글 `return_type_code`는 `source_label`로 영문 코드에 매핑됩니다.

| 데이터셋 값 | 코드 | 건수(전체) |
|---|---|---|
| 단순 변심 | `CHANGE_OF_MIND` | 62 |
| 사이즈/핏 | `SIZE_FIT` | 36 |
| 불량 제품 | `DEFECTIVE` | 34 |
| 색상/사진 차이 | `COLOR_IMAGE` | 24 |
| 바느질/마감 | `QUALITY_FINISH` | 10 |
| 원단/감촉 | `FABRIC_FEEL` | 8 |
| 기타 | `OTHER` | 5 |
| 배송/포장 | `SHIPPING` | 5 |

> `DEFECTIVE`(불량 제품)와 `QUALITY_FINISH`(바느질/마감)를 **분리해 둡니다.** 전자는 입고 검수 불량과 교차 대조할 범주이고, 후자는 고객 체감 불만이라 성격이 다릅니다. 합치면 "반품 품질 의견 ⇄ 입고 봉제 불량" 대조가 흐려집니다.

## 금지 사항 — 예나가 검증

| # | 금지 | 검증 방법 |
|---|---|---|
| 1 | `evidence_quotes`에 **입력에 없는 문장** 생성 | 모든 인용이 `return_detail_text`에 존재하는지 문자열 대조 |
| 2 | `evidence_order_ids`에 없는 ID | 입력 `order_id` 집합 포함 확인 |
| 3 | 근거 없는 수치 | `analyzed_count`·`categories[].count` 산술 일치 확인 |
| 4 | `possible_causes`를 확정적으로 표현 | "~이다", "~때문이다" 금지 → "~가능성", "~로 보입니다" |
| 5 | `enums.json`에 없는 코드 | 열거형 대조 |
| 6 | 근거 부족인데 원인 제시 | `insufficient_data: true`면 `possible_causes`는 `[]` |
| 7 | 거래처 변경·패턴 변경을 **권고** | 체크리스트는 "검토", "확인" 수준까지만 |

근거가 부족할 때는 `insufficient_data: true` + `notes`에 `AI_UNCERTAIN`("판단하기 어려움").

## 🔴 폴백 — 예나 최우선

LLM 호출이 실패·지연되면 `fallback/returns-analyze.json`을 **200으로** 반환합니다.

- **P002**에 대응하는 실제 분석 결과를 손으로 작성
- `"fallback": true`를 담고 `notes`에 안내 문구 추가
- 백엔드는 LLM 예외를 잡아 이 파일을 그대로 반환

> **이게 시연 보험입니다.** 다른 AI 작업보다 먼저 끝내세요. 심사 중 네트워크나 API가 불안정해도 데모가 끝까지 돌아갑니다.
> 이 파일은 `FE/src/mocks/returns-analyze.json`과 내용이 같아도 됩니다.

## 역할 분담

| | 서영 | 예나 |
|---|---|---|
| 먼저 | 입출력 JSON 스키마 ✅ | **폴백 응답** 🔴 |
| 다음 | 프롬프트 ✅ → 실제 LLM 호출 검증 | 검증 스크립트, 테스트 케이스 |
| 이후 | 분류 품질 개선 | **FE 반품 분석 화면** |

## 접점

| 상대 | 협의 내용 |
|---|---|
| 태연 (BE) | 호출 방식, 입력 구성, 출력 검증 위치 |
| 윤지 (FE) | 네 블록을 화면에서 어떻게 보여줄지 |
| 시환 (DATA) | 반품 사유 분류 체계, `defects.csv` 불량 유형과의 대조 |
