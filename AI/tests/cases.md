# AI 출력 검증 테스트 기록

## 1. 자동 출력 검증

- 검증일: 2026-10-24
- 검증 코드: AI/tests/test_output_verification.py
- 재사용 함수: AI/prompts/run_analysis.py의 verify()

### 실행 명령
python -m unittest discover -s AI/tests -p "test_output_verification.py" -v

### 실행 결과
- 총 테스트: 18개
- 성공: 18개
- 실패: 0개
- 결과: OK

### 주요 검증 내용
- JSON 스키마 검증
- 반품 유형별 건수 검증
- 근거 원문 존재 여부 확인
- 주문번호 존재 여부 확인
- 잘못된 분류 코드 검출
- evidence_quotes 빈 배열 검출
- evidence_order_ids 빈 배열 검출
- insufficient_data 역방향 검증
- 데이터 부족 시 원인 생성 여부 확인
- 원본 CSV의 8개 고객 선택 사유가 enums.json의 8개 유형과 모두 대응하는지 확인
- 예외 문장(상충된 핏 의견, 선물 일정 취소, 구체적 사유가 없는 기타)의 원문 인용 및 order_id 검증

### 상품별 검증
- P002: 기존 fallback JSON 및 스키마 검증 통과
- P007: 데이터 부족 상황의 테스트 출력 검증 통과
- P001, P003, P004, P005, P006, P008:
  원본 데이터로 구성한 테스트 fixture의 출력 검증 통과

### 결과 해석 및 범위
- 이 테스트는 `verify()`의 구조·코드·집계·근거 검증을 확인합니다.
- 테스트 출력은 원본 CSV의 고객 선택 사유로 만든 검증용 fixture이며, AI 분류 결과가 아닙니다.
- 이번 실행에서는 실제 AI/LLM을 호출하지 않았으므로 반품 사유 분류 성공이나 정확도를 기록하지 않습니다.
- 실제 AI 분류 정확도는 AI 응답을 실행·보관한 뒤 별도 기대 라벨과 비교해야 합니다.
- `verify()`는 인용문과 order_id가 각각 입력에 존재하는지 검증하지만, 두 값이 같은 원본 행에 속하는지까지 검증하지 않습니다.

## 2. 원본 문장과 실제 LLM 분류 비교

- 검증 코드: `AI/tests/test_return_classification.py`
- 예상 분류 기준: 원본 CSV의 `return_type_code`를 `DATA/enums.json`으로 매핑한 코드
- 케이스: 8개 유형별 대표 문장 1개씩 + 예외 문장 4개
- 개인정보 최소화: API 요청에 주문번호와 상품 ID는 포함하지 않음
- 실행 명령: `python -m unittest discover -s AI/tests -p "test_return_classification.py" -v`

### 실행 결과

**1차 (예나, 2026-10-24)**
- 상태: **미실행**
- 사유: 실행 환경에 `.env` 파일과 `LLM_API_KEY` 환경 변수가 모두 없음
- 실제 LLM 호출: 없음
- 오분류: **측정 불가 (미실행; 성공/실패로 간주하지 않음)**

**2차 (서영, 2026-10-24) — 키를 설정하고 재시도**
- 상태: **미실행**
- 사유: **Gemini API 장애.** 키·모델 설정은 정상이었으나 API가 응답하지 않음
  - 1회차: `HTTP 503 Service Unavailable`
  - 2회차: 재시도 적용 후에도 180초 타임아웃
  - 최소 ping 요청(`"reply with pong"`)조차 60초 타임아웃 → **우리 코드가 아닌 외부 장애**
- 같은 키로 **직전까지는 호출이 성공**했습니다 (`AI/prompts/sample-output-P002.json`,
  `sample-output-P007.json`, `/api/returns/analyze` 실호출). 일시적 장애로 판단합니다.
- 오분류: **측정 불가 (미실행)**

> 🔴 **재실행 필요.** API가 복구되면 아래 명령 한 줄로 끝납니다. 결과가 나오면 이 절을 갱신하세요.
>
> ```bash
> python -m unittest discover -s AI/tests -p "test_return_classification.py" -v
> ```
>
> 케이스별 `expected` / `actual` / `일치·오분류`가 출력됩니다.

### 비교 기준 및 범위
- 8개 대표 문장은 각 `return_type_code`별 원본 자유 서술 중 가장 자주 등장한 문장으로 구성합니다.
- 예외 케이스는 상충된 핏 표현, 선물 일정 취소, 사유가 불명확한 기타, 기대와 다른 느낌의 문장입니다. 기대 코드는 각 원본 CSV 행의 선택 사유를 사용합니다.
- 고객 선택 사유는 독립적으로 사람 검수한 정답 라벨이 아니라 비교용 기준입니다. 따라서 불일치는 모델 오류 후보로 기록하되, 선택 사유 자체의 오분류 가능성도 고려해야 합니다.
- API 설정 후 위 명령을 실행하면 케이스별 `expected` / `actual` / `일치·오분류`가 출력됩니다. 이 실행 기록은 실제 응답을 확인한 뒤에만 갱신합니다.

---

## 3. 테스트 인프라 수정 (서영, 2026-10-24)

실행해 보니 **실패가 성공처럼 보이는 문제**가 두 군데 있었습니다. 둘 다 고쳤습니다.

### 3-1. `jsonschema` 의존성 미선언

- 증상: `test_p002_fallback_full_json_schema`가 `ModuleNotFoundError`로 떨어져
  전체가 `FAILED (errors=1)`로 표시됨. 테스트가 깨진 것처럼 보임
- 원인: `jsonschema`가 어느 requirements 파일에도 없었음
- 조치
  - [`AI/requirements.txt`](../requirements.txt) 신설로 의존성 선언
  - 미설치 시 **에러가 아니라 skip** 되도록 변경

```
jsonschema 있음 → Ran 18 tests ... OK
jsonschema 없음 → Ran 18 tests ... OK (skipped=1)
```

### 3-2. LLM 호출에 재시도가 없었음 🔴

- 증상: `HTTP 503`이 나면 **즉시 `skipTest`** → 결과가 `OK (skipped=1)`
- 문제: 일시적 과부하가 **통과처럼 보입니다.** 키가 없어서 건너뛴 것과
  API가 잠시 죽어서 건너뛴 것이 **출력상 구분되지 않습니다.**
  이 때문에 분류 검증이 한 번도 실행되지 않은 채 남아 있을 수 있습니다
- 조치: `classify_with_gemini()`에 재시도 추가
  (503·429·500, 최대 2회, 5초→10초. [`AI/prompts/run_analysis.py`](../prompts/run_analysis.py)와 동일 정책)

### 3-3. 현재 통과 상태

| 항목 | 결과 |
|---|---|
| `test_output_verification.py` | **18개 통과** (jsonschema 미설치 시 17 통과 + 1 skip) |
| `validate_output.py` | `[PASS] 자동 출력 검증 통과 / 검토 알림 1개` |
| `test_return_classification.py` | **미실행** — API 장애 (§2 참고) |

### 3-4. 시연 관점에서의 함의

개발 중 Gemini API가 **503 → 타임아웃 → 무응답**으로 악화됐습니다.
`AI/fallback/returns-analyze.json`이 없었다면 그 시간 동안 시연이 불가능했습니다.

**폴백이 선택이 아니라 필수라는 점이 실제로 증명됐습니다.**
다만 폴백은 HTTP 200으로 정상 응답처럼 보이므로, 화면이나 로그에서
`"fallback": true` 여부를 **반드시 구분**할 수 있어야 합니다.