# AI — 반품 원인 분석

**담당:** 서영 (분석·프롬프트·스키마) · 예나 (검증·폴백·테스트)

🔴 **AI는 반품 원인 분석 한 곳에만 씁니다.** 불량률·재고·수익성은 공식 계산입니다 ([`DATA/metrics.md`](../DATA/metrics.md)).

## 폴더

```
AI/
├── prompts/     return-analysis.md          ← 서영, 3:00
├── schemas/     return-analysis.schema.json ← 서영, 1:00
├── fallback/    returns-analyze.json        ← 예나, 1:30 🔴
└── tests/       cases.md                    ← 예나, 3:00
```

## 입력 (백엔드 → LLM)

백엔드가 DB에서 모아 프롬프트에 넣습니다. **원본 CSV를 그대로 넣지 않습니다.**

| 필드 | 용도 |
|---|---|
| `product`, `period`, `stats` | 맥락 (상품명, 기간, 판매·반품 수량, 반품률) |
| `reviews[]` | **분류 대상.** 고객이 작성한 자유 서술 (`returns.review_text`) + `return_id` |
| `selected_reasons[]` | 고객이 **선택한** 사유. 분류 결과와 대조용 — 분류 입력이 아님 |
| `defect_context[]` | 입고 검수 불량 유형. `품질·마감` 반품과 방향이 같은지 확인용 |

> `reviews`가 비어 있으면 LLM을 호출하지 않고 `insufficient_data: true`를 즉시 반환합니다.

## 출력 — 네 블록을 반드시 분리

관측된 사실과 AI 추정을 섞으면 안 됩니다.

| 블록 | 필드 | 성격 |
|---|---|---|
| 관측된 사실 | `observed_facts` | 데이터에서 직접 확인되는 수치. **근거 원문 필수** |
| 가능한 원인 | `possible_causes` | 단정하지 않는 후보. `confidence` 필수 |
| 추가 확인 사항 | `checks_needed` | 사용자가 직접 확인할 것 |
| 개선 체크리스트 | `improvement_checklist` | 등록 가능한 작업. `PAGE_FIX` / `PRODUCT_FIX` 구분 |

```json
{
  "product_id": "P001",
  "analyzed_count": 8,
  "categories": [
    { "code": "SIZE_FIT", "label": "사이즈·핏 문제", "count": 4, "share_pct": 50.0 }
  ],
  "observed_facts": [
    {
      "statement": "반품 8건 중 4건(50.0%)이 사이즈·핏 문제로 분류되었고, \"허벅지\" 언급이 3건 반복됩니다",
      "evidence_quotes": ["허벅지가 끼어서 반품합니다", "허벅지 부분이 너무 좁아요"],
      "evidence_return_ids": ["R0012", "R0019"]
    }
  ],
  "possible_causes": [
    {
      "statement": "허벅지 둘레 실측 또는 사이즈 안내가 고객 기대와 다를 가능성",
      "confidence": "MEDIUM",
      "related_categories": ["SIZE_FIT"]
    }
  ],
  "checks_needed": ["사이즈별 허벅지 둘레 실측 치수 확인"],
  "improvement_checklist": [
    { "title": "상품 페이지에 실측 치수 추가", "type": "PAGE_FIX", "rationale": "..." },
    { "title": "다음 샘플 전 패턴 검토", "type": "PRODUCT_FIX", "rationale": "..." }
  ],
  "insufficient_data": false,
  "fallback": false,
  "notes": []
}
```

분류 코드는 [`DATA/enums.json`](../DATA/enums.json)의 `return_reasons` 7종만 씁니다.
`improvement_checklist[].type` — `PAGE_FIX`(상품 설명 개선) / `PRODUCT_FIX`(실제 상품 수정)를 구분합니다.

## 금지 사항 — 예나가 검증

| # | 금지 | 검증 방법 |
|---|---|---|
| 1 | `evidence_quotes`에 **입력에 없는 문장** 생성 | 모든 인용이 `reviews[].text`에 존재하는지 문자열 대조 |
| 2 | `evidence_return_ids`에 없는 ID | 입력 `return_id` 집합 포함 확인 |
| 3 | 근거 없는 수치 | `analyzed_count`·`categories[].count` 산술 일치 확인 |
| 4 | `possible_causes`를 확정적으로 표현 | "~이다", "~때문이다" 금지 → "~가능성", "~로 보입니다" |
| 5 | `enums.json`에 없는 코드 | 열거형 대조 |
| 6 | 근거 부족인데 원인 제시 | `insufficient_data: true`면 `possible_causes`는 `[]` |
| 7 | 거래처 변경·패턴 변경을 **권고** | 체크리스트는 "검토", "확인" 수준까지만 |

근거가 부족할 때는 `insufficient_data: true` + `notes`에 `AI_UNCERTAIN`("판단하기 어려움").

## 🔴 폴백 — 예나 최우선 (1:30)

LLM 호출이 실패·지연되면 `fallback/returns-analyze.json`을 **200으로** 반환합니다.

- 데모 데이터의 `P001`에 대응하는 실제 분석 결과를 손으로 작성
- `"fallback": true`를 담고 `notes`에 안내 문구 추가
- 백엔드는 LLM 예외를 잡아 이 파일을 그대로 반환

> **이게 시연 보험입니다.** 다른 AI 작업보다 먼저 끝내세요. 심사 중 네트워크나 API가 불안정해도 데모가 끝까지 돌아갑니다.
> 이 파일은 `FE/src/mocks/returns-analyze.json`과 내용이 같아도 됩니다.

## 역할 분담

| | 서영 | 예나 |
|---|---|---|
| 1:00 | 입출력 JSON 스키마 확정 | — |
| 1:30 | — | **폴백 응답** 🔴 |
| 3:00 | 프롬프트 작성, 체크리스트 생성 | 검증 스크립트, 테스트 케이스 |
| 이후 | 분류 품질 개선 | **FE 반품 분석 화면** |

## 접점

| 상대 | 협의 내용 |
|---|---|
| 태연 (BE) | 호출 방식, 입력 구성, 출력 검증 위치 |
| 윤지 (FE) | 네 블록을 화면에서 어떻게 보여줄지 |
| 시환 (DATA) | 반품 사유 분류 체계, 테스트용 반품 문장 |
