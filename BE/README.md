# BE — 백엔드

**담당:** 태연 · **스택:** FastAPI + SQLite

4개 영역의 지표를 계산해 제공하고, AI 기능과 프론트엔드를 연결합니다.

## 폴더

```
BE/
├── docs/api.md       API 명세 ← 태연 소유
└── app/
    ├── models/       SQLite 테이블 8개
    ├── schemas/      요청·응답 모델 (Pydantic)
    ├── services/     지표 계산 — defect / inventory / profit / returns
    ├── routers/      API 엔드포인트
    └── importers/    CSV 적재·검증
```

## 테이블 8개

**DB 설계에 시간을 쓰지 말고 이 구조를 그대로 쓰세요.**

| 테이블 | 설명 | 쓰이는 영역 |
|---|---|---|
| `products` | 상품, 판매가, 원가, 리드타임, MOQ | 전체 |
| `suppliers` | 거래처 | 불량률 |
| `purchase_orders` | 발주·입고·검수·불량 수량 | 불량률, 재고·발주 |
| `defects` | 불량 유형별 수량 | 불량률 |
| `sales` | 판매일·수량·채널·금액 | 재고·발주, 정산 |
| `returns` | 반품 수량·사유·후기·재판매 가능 | 반품, 재고, 정산 |
| `costs` | 수수료율, 광고비, 배송비, 반품 처리비 | 정산 |
| `tasks` | 개선 조치, 담당자, 마감일, 상태 | 반품, 불량률 |

> **재고는 테이블을 만들지 않고 계산으로 구합니다** — 양품 입고 − 판매 + 재판매 가능 반품.
> 컬럼 정의는 [`DATA/dictionary.md`](../DATA/dictionary.md)를 그대로 따릅니다.

## 지표 계산

[`DATA/metrics.md`](../DATA/metrics.md)의 공식을 **그대로** 구현합니다. 공식이 다르면 코드가 아니라 그 문서를 먼저 고칩니다.

🔴 **모든 지표 응답에 `inputs`와 `formula`를 담습니다.** 결과값만 반환하면 화면에서 근거를 못 보여줍니다.

## 태연이 정할 것

| 결정 | 합의 | 산출 |
|---|---|---|
| API 경로·요청·응답 | ✅ 전원 | [`docs/api.md`](./docs/api.md) |
| 에러 형식·HTTP 코드 | 아니오 | [`docs/api.md`](./docs/api.md) |
| 🔴 **mock 응답 JSON 10개** | 아니오 | `FE/src/mocks/*.json` ← **윤지가 이걸 기다림** |
| 환경변수 이름 | 아니오 | [`.env.example`](../.env.example) |
| JSON 공통 규약 | ✅ 전원 | [`CONVENTIONS.md`](../CONVENTIONS.md) |

## 지켜야 할 것

- 키는 `snake_case`, 비율은 0~100 + `_pct`, 금액은 정수, ID는 문자열 → [`CONVENTIONS.md`](../CONVENTIONS.md)
- 계산 불가는 `0`이 아니라 `null` + `notes`
- 🔴 **LLM 호출 실패는 에러로 반환하지 않습니다.** `AI/fallback/returns-analyze.json`을 200으로 반환합니다
- 🔴 **AI API 키는 서버 환경변수로만** 관리합니다
- 데모 데이터를 **앱 시작 시 시드**합니다 — 업로드가 실패해도 시연이 되어야 합니다

## 실행

```bash
cd BE
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # 값 채우기
uvicorn app.main:app --reload  # http://localhost:8000/docs
```

## 접점

| 상대 | 협의 내용 |
|---|---|
| 윤지 (FE) | 응답 형식 — mock JSON이 계약 |
| 서영·예나 (AI) | AI 입력 구성과 출력 스키마 검증 |
| 시환 (DATA) | 컬럼 정의, 지표 공식, 검증 기대값 |
