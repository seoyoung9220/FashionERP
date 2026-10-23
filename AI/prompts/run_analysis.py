#!/usr/bin/env python3
"""
반품 분석 프롬프트를 실제 LLM 에 돌리고 출력을 검증한다.

키는 .env 의 LLM_API_KEY 에서 읽는다. 인자로 받지 않는다(쉘 기록에 남으므로).

사용:
    python3 AI/prompts/run_analysis.py P002
    python3 AI/prompts/run_analysis.py P007 -o /tmp/out-P007.json
    python3 AI/prompts/run_analysis.py P002 --dry-run     # 호출 없이 페이로드만 출력

.env 예시:
    LLM_API_KEY=...
    LLM_MODEL=gemini-3.8-flash        # 생략 시 이 값

검증 항목 (AI/README.md 금지 사항 중 기계 검사 가능한 것):
    1. 스키마 required / 스키마 외 필드
    2. categories[].count 합 == analyzed_count
    3. evidence_quotes 가 입력 원문에 글자 그대로 존재
    4. evidence_order_ids 가 입력 order_id 에 존재
    5. 열거형 코드가 enums.json 에 존재
    6. insufficient_data=true 이면 possible_causes / improvement_checklist 가 빈 배열
    7. possible_causes 에 단정 표현("~이다", "~때문이다") 사용 여부
    8. observed_facts 의 evidence 가 비어 있지 않은지 (스키마 minItems:1)
    9. categories[].label 이 enums.json 과 일치하는지
"""
import json, os, re, sys, time, pathlib, argparse, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "AI/schemas/return-analysis.schema.json"
ENUMS = ROOT / "DATA/enums.json"
PROMPT_MD = ROOT / "AI/prompts/return-analysis.md"
DEFAULT_MODEL = "gemini-3.8-flash"


def load_env():
    p = ROOT / ".env"
    if not p.exists():
        sys.exit(f".env 가 없습니다. `cp .env.example .env` 후 LLM_API_KEY 를 채우세요.")
    env = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("LLM_API_KEY"):
        sys.exit(".env 의 LLM_API_KEY 가 비어 있습니다.")
    return env


def system_prompt():
    """return-analysis.md 의 첫 번째 ````text 블록(System 프롬프트)을 추출."""
    md = PROMPT_MD.read_text(encoding="utf-8")
    m = re.search(r"## System 프롬프트\s*\n+````text\n(.*?)\n````", md, re.S)
    if not m:
        sys.exit("return-analysis.md 에서 System 프롬프트 블록을 찾지 못했습니다.")
    return m.group(1)


def to_gemini_schema(node):
    """JSON Schema → Gemini responseSchema (OpenAPI 서브셋).

    Gemini 는 additionalProperties / $schema / $id / minLength / pattern 등을
    받지 않는다. 지원되는 키만 남기고 enum 은 string 타입으로 변환한다.
    """
    if not isinstance(node, dict):
        return node
    if "enum" in node:
        return {"type": "string", "enum": node["enum"]}
    t = node.get("type")
    out = {}
    if t:
        out["type"] = t.upper() if t != "number" else "NUMBER"
        out["type"] = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER",
                       "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT"}[t]
    if "description" in node:
        out["description"] = node["description"][:300]
    if t == "object":
        out["properties"] = {k: to_gemini_schema(v) for k, v in node.get("properties", {}).items()}
        if node.get("required"):
            out["required"] = node["required"]
    if t == "array":
        out["items"] = to_gemini_schema(node.get("items", {}))
    return out


def call_gemini(key, model, sys_prompt, payload, schema):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {
        "systemInstruction": {"parts": [{"text": sys_prompt}]},
        "contents": [{"role": "user", "parts": [{"text":
            "아래 상품의 반품 데이터를 분석해 주세요.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    # 503(과부하) / 429(레이트리밋) 는 일시적이므로 재시도한다.
    # 그래도 실패하면 백엔드는 AI/fallback/returns-analyze.json 을 200 으로 반환해야 한다.
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.load(r)
            break
        except urllib.error.HTTPError as e:
            last = f"API 오류 {e.code}: {e.read().decode()[:400]}"
            if e.code not in (429, 500, 503) or attempt == 2:
                sys.exit(last)
            wait = 5 * (attempt + 1)
            print(f"  {e.code} — {wait}초 후 재시도 ({attempt + 1}/2)", file=sys.stderr)
            time.sleep(wait)
        except urllib.error.URLError as e:
            sys.exit(f"네트워크 오류: {e.reason}")
    else:
        sys.exit(last)
    try:
        return json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        sys.exit("응답 파싱 실패:\n" + json.dumps(res, ensure_ascii=False)[:1500])


def verify(out, payload):
    schema = json.load(open(SCHEMA, encoding="utf-8"))
    enums = json.load(open(ENUMS, encoding="utf-8"))
    codes = {e["code"] for e in enums["return_reasons"]}
    quotes = {r["text"] for r in payload["returns"]}
    oids = {i for r in payload["returns"] for i in r.get("order_ids", [r.get("order_id")])}
    f = []

    for k in schema["required"]:
        if k not in out:
            f.append(f"required 누락: {k}")
    for k in out:
        if k not in schema["properties"]:
            f.append(f"스키마 외 필드: {k}")

    tot = sum(c.get("count", 0) for c in out.get("categories", []))
    if tot != out.get("analyzed_count"):
        f.append(f"categories 합 {tot} != analyzed_count {out.get('analyzed_count')}")
    for c in out.get("categories", []):
        if c.get("code") not in codes:
            f.append(f"미등록 코드: {c.get('code')}")
        if not (0 <= c.get("share_pct", -1) <= 100):
            f.append(f"share_pct 범위 밖: {c.get('share_pct')}")

    labels = {e["code"]: e["label"] for e in enums["return_reasons"]}
    for c in out.get("categories", []):
        if c.get("code") in labels and c.get("label") != labels[c["code"]]:
            f.append(f"label 불일치 {c['code']}: '{c.get('label')}' (enums: '{labels[c['code']]}')")

    for i, fact in enumerate(out.get("observed_facts", []), 1):
        # 스키마 minItems: 1 — 근거 없는 사실 금지
        if not fact.get("evidence_quotes"):
            f.append(f"observed_facts[{i}] evidence_quotes 가 비어 있음 (근거 없는 사실)")
        if not fact.get("evidence_order_ids"):
            f.append(f"observed_facts[{i}] evidence_order_ids 가 비어 있음")
        for q in fact.get("evidence_quotes", []):
            if q not in quotes:
                f.append(f"환각 인용: {q[:40]}")
        for o in fact.get("evidence_order_ids", []):
            if o not in oids:
                f.append(f"없는 order_id: {o}")

    if out.get("insufficient_data"):
        if out.get("possible_causes"):
            f.append("insufficient_data=true 인데 possible_causes 가 비어 있지 않음")
        if out.get("improvement_checklist"):
            f.append("insufficient_data=true 인데 improvement_checklist 가 비어 있지 않음")

    for c in out.get("possible_causes", []):
        if re.search(r"(때문이다|때문입니다|입니다\.$|이다\.$)", c.get("statement", "")):
            f.append(f"단정 표현 의심: {c['statement'][:50]}")
    return f


def findings(out):
    """P002 에서 기대하는 발견이 나왔는지 (AI/prompts/return-analysis.md)."""
    txt = json.dumps(out, ensure_ascii=False)
    return {
        "사이즈 상충 발견": bool(re.search(r"(작|타이트|좁).{0,40}(크|넓)|(크|넓).{0,40}(작|타이트|좁)", txt)),
        "사이즈 집중 없음 언급": "집중" in txt or "고르" in txt or bool(out.get("size_color_findings")),
        "교차 대조(cross_check)": "cross_check" in out,
        "PAGE_FIX / PRODUCT_FIX 둘 다": len({t.get("type") for t in out.get("improvement_checklist", [])}) == 2,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("product_id")
    ap.add_argument("-o", "--out")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, str(ROOT / "AI/prompts"))
    from build_input import build

    payload = build(a.product_id)
    if a.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2)); sys.exit()

    env = load_env()
    model = env.get("LLM_MODEL") or DEFAULT_MODEL
    gschema = to_gemini_schema(json.load(open(SCHEMA, encoding="utf-8")))

    print(f"모델 {model} · 상품 {a.product_id} · 반품 {payload['stats']['return_count']}건 "
          f"({len(payload['returns'])}그룹) 호출 중…", file=sys.stderr)
    out = call_gemini(env["LLM_API_KEY"], model, system_prompt(), payload, gschema)

    path = a.out or f"/tmp/out-{a.product_id}.json"
    pathlib.Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    fails = verify(out, payload)
    print("\n=== 검증 ===")
    print("  통과 ✅" if not fails else "\n".join(f"  ❌ {x}" for x in fails))
    if a.product_id == "P002":
        print("\n=== P002 기대 발견 ===")
        for k, v in findings(out).items():
            print(f"  {'✅' if v else '❌'} {k}")
    print(f"\n출력: {path}")
