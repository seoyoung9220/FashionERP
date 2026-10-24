"""AI 반품 원인 분석 (api.md: POST /api/returns/analyze).

참조 구현: AI/prompts/run_analysis.py, AI/prompts/build_input.py (서영·예나, 실제 LLM 검증 완료)
그 코드를 백엔드용으로 옮긴 것입니다. 바뀐 점은 "실패하면 프로그램 종료" 대신
"실패하면 폴백 반환"으로 바꾼 것뿐입니다.

호출 설정 (팀 합의)
  모델 gemini-3.8-flash (LLM_MODEL 로 변경 가능) · temperature 0.1
  responseMimeType application/json · responseSchema = 변환된 스키마
  System 프롬프트는 systemInstruction 에 분리 · timeout 180초
  재시도: 429/500/503 만 2회 (5초 → 10초), 그 외는 즉시 실패

🔴 어떤 실패든 AI/fallback/returns-analyze.json 을 "fallback": true 로 200 반환합니다.
🔴 API 키는 서버 환경변수(.env 의 LLM_API_KEY)에서만 읽습니다.
"""
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter, OrderedDict

from app import enums
from app.config import AI_FALLBACK_JSON, LLM_API_KEY, LLM_MODEL, REPO_DIR
from app.utils import note, pct

SCHEMA_JSON = REPO_DIR / "AI" / "schemas" / "return-analysis.schema.json"
PROMPT_MD = REPO_DIR / "AI" / "prompts" / "return-analysis.md"
DEFAULT_MODEL = "gemini-3.8-flash"
TIMEOUT_SEC = 180
RETRY_CODES = (429, 500, 503)
RETRY_WAITS = (5, 10)

# 다른 곳에서 바꿔 끼울 수 있게 함수 이름으로 둡니다 (테스트에서 실제 호출 대신 사용)
_sleep = time.sleep


class AIFailed(Exception):
    """LLM 호출·검증 실패. 잡아서 폴백으로 바꿉니다."""


# ───────────────────────── 폴백 ─────────────────────────

def _fallback(reason: str | None = None) -> dict:
    try:
        data = json.loads(AI_FALLBACK_JSON.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        # 폴백 파일조차 없을 때도 시연이 멈추지 않게 최소 응답을 보냅니다
        data = {"insufficient_data": True, "notes": [note("AI_UNCERTAIN")]}
    data["fallback"] = True
    if reason:
        print(f"[ai] 폴백 반환: {reason}")   # 서버 로그에만 남깁니다 (원인 파악용)
    return data


# ───────────────────────── 입력 만들기 (build_input.py 와 같은 구조) ─────────────────────────

def build_payload(conn, product_id: str, period: dict) -> dict | None:
    """정본 주문 데이터(DB의 sales/returns)에서 LLM 입력을 만듭니다. 주문이 없으면 None."""
    orders = conn.execute(
        "SELECT * FROM sales WHERE product_id = ? AND sold_at BETWEEN ? AND ? ORDER BY sold_at, order_id",
        [product_id, period["from"], period["to"]],
    ).fetchall()
    if not orders:
        return None
    rets = conn.execute(
        """SELECT s.order_id, s.size, s.color, r.return_type_code, r.return_detail_text
           FROM returns r JOIN sales s ON s.order_id = r.order_id
           WHERE s.product_id = ? AND s.sold_at BETWEEN ? AND ?
           ORDER BY s.sold_at, s.order_id""",
        [product_id, period["from"], period["to"]],
    ).fetchall()

    # 고객이 선택한 사유: 원본 데이터의 한글 값(source_label)으로 되돌려 보냅니다
    src = {it["code"]: (it["source_labels"][0] if it["source_labels"] else it["label"])
           for it in enums.load()["return_types"]}
    selected = [{"source_label": src.get(c, c or "NA"), "count": n}
                for c, n in Counter(r["return_type_code"] for r in rets).most_common()]

    # 같은 문장을 묶어 토큰 절약. order_ids 는 근거라 반드시 유지
    groups: OrderedDict[str, list] = OrderedDict()
    for r in rets:
        if r["return_detail_text"]:
            groups.setdefault(r["return_detail_text"], []).append(r)
    items = [{"text": t, "count": len(v), "order_ids": [x["order_id"] for x in v],
              "sizes": sorted({x["size"] for x in v}), "colors": sorted({x["color"] for x in v})}
             for t, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]

    dims = {}
    for d in ("size", "color"):
        c = Counter(r[d] for r in rets)
        dims[d] = [{"value": k, "count": v, "share_pct": pct(v, len(rets))} for k, v in c.most_common()]

    po_ids = [r[0] for r in conn.execute("SELECT po_id FROM purchase_orders WHERE product_id = ?", [product_id])]
    dc = Counter()
    if po_ids:
        marks = ",".join("?" for _ in po_ids)
        for row in conn.execute(f"SELECT defect_type, defect_qty FROM defects WHERE po_id IN ({marks})", po_ids):
            dc[row[0]] += row[1]
    total_defect = sum(dc.values())

    dates = [o["sold_at"] for o in orders]
    return {
        "product": {"product_id": product_id, "product_name": orders[0]["product_name"],
                    "category": orders[0]["category"]},
        "period": {"from": dates[0], "to": dates[-1]},
        "stats": {"order_count": len(orders), "return_count": len(rets),
                  "return_rate_pct": pct(len(rets), len(orders))},
        "selected_reasons": selected,
        "returns": items,
        "dimension_counts": dims,
        "defect_context": [{"code": k, "label": enums.label("defect_types", k) or k, "qty": v,
                            "share_pct": pct(v, total_defect)} for k, v in dc.most_common()],
        "defect_context_note": (
            f"{product_id} 의 발주 {len(po_ids)}건 입고 검수에서 확인된 불량 {total_defect}장. "
            "반품 건과 같은 물량인지는 확인되지 않았으므로 단정하지 말 것."
        ) if total_defect else None,
    }


# ───────────────────────── 프롬프트·스키마 (run_analysis.py 와 같음) ─────────────────────────

def system_prompt() -> str:
    md = PROMPT_MD.read_text(encoding="utf-8")
    m = re.search(r"## System 프롬프트\s*\n+````text\n(.*?)\n````", md, re.S)
    if not m:
        raise AIFailed("return-analysis.md 에서 System 프롬프트 블록을 찾지 못함")
    return m.group(1)


def to_gemini_schema(node):
    """Gemini 는 additionalProperties·$schema·$id·pattern·minLength 를 거부합니다 → 지원 키만 남김"""
    if not isinstance(node, dict):
        return node
    if "enum" in node:
        return {"type": "STRING", "enum": node["enum"]}
    t = node.get("type")
    out = {}
    if t:
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


def call_gemini(key: str, model: str, sys_prompt: str, payload: dict, schema: dict) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": sys_prompt}]},
        "contents": [{"role": "user", "parts": [{"text":
            "아래 상품의 반품 데이터를 분석해 주세요.\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": schema},
    }
    data = json.dumps(body).encode()
    for attempt in range(len(RETRY_WAITS) + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
                res = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or attempt == len(RETRY_WAITS):
                raise AIFailed(f"API 오류 {e.code}") from None   # 키가 들어간 URL은 남기지 않음
            print(f"[ai] {e.code} — {RETRY_WAITS[attempt]}초 후 재시도 ({attempt + 1}/{len(RETRY_WAITS)})")
            _sleep(RETRY_WAITS[attempt])
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AIFailed(f"네트워크 오류: {type(e).__name__}") from None
    try:
        return json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        raise AIFailed("응답 파싱 실패") from None


# ───────────────────────── 백엔드 검사 (run_analysis.verify 기반) ─────────────────────────

def check_output(out: dict, payload: dict, schema: dict) -> dict:
    """심각한 문제는 AIFailed(→폴백). 근거 없는 사실 등은 걸러내고 AI_UNCERTAIN 을 붙입니다."""
    if not isinstance(out, dict):
        raise AIFailed("출력이 객체가 아님")
    missing = [k for k in schema.get("required", []) if k not in out and k != "fallback"]
    if missing:
        raise AIFailed(f"required 누락: {missing}")
    out = {k: v for k, v in out.items() if k in schema.get("properties", {})}   # 스키마 외 필드 제거

    codes = enums.codes("return_types")
    cats = out.get("categories") or []
    if any(c.get("code") not in codes for c in cats):
        raise AIFailed("미등록 분류 코드")
    if sum(c.get("count", 0) for c in cats) != out.get("analyzed_count"):
        raise AIFailed("categories 합계 ≠ analyzed_count")
    for c in cats:                      # 모델이 한글 사유명을 그대로 보내는 경우가 있어 라벨은 enums 로 덮어씀
        c["label"] = enums.label("return_types", c["code"])

    # 🔴 Gemini 는 minItems 를 강제하지 않음 → 근거 없는 사실·없는 인용·없는 order_id 를 직접 걸러냄
    quotes = {r["text"] for r in payload["returns"]}
    oids = {o for r in payload["returns"] for o in r["order_ids"]}
    kept, dropped = [], 0
    for f in out.get("observed_facts") or []:
        q, o = f.get("evidence_quotes") or [], f.get("evidence_order_ids") or []
        if q and o and all(x in quotes for x in q) and all(x in oids for x in o):
            kept.append(f)
        else:
            dropped += 1
    out["observed_facts"] = kept

    notes = list(out.get("notes") or [])
    if dropped:
        notes.append({"code": "AI_UNCERTAIN", "message": f"근거를 확인할 수 없는 관측 {dropped}건을 제외했습니다"})
    if out.get("insufficient_data"):    # 근거 부족이면 원인·체크리스트를 내보내지 않음 (AI/README 금지 사항)
        out["possible_causes"], out["improvement_checklist"] = [], []
        if not any(n.get("code") == "SMALL_SAMPLE" for n in notes):
            notes.append(note("SMALL_SAMPLE"))
    out["notes"] = notes
    return out


# ───────────────────────── 진입점 ─────────────────────────

def analyze_returns(conn, product_id: str, period: dict, caller=None) -> dict:
    """caller: 테스트에서 실제 Gemini 대신 넣는 가짜 함수 (평소에는 None)"""
    if not LLM_API_KEY and caller is None:
        return _fallback("LLM_API_KEY 없음")
    try:
        payload = build_payload(conn, product_id, period)
        if payload is None:
            return _fallback(f"{product_id} 주문 없음")
        schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        call = caller or call_gemini
        raw = call(LLM_API_KEY, LLM_MODEL or DEFAULT_MODEL, system_prompt(), payload, to_gemini_schema(schema))
        result = check_output(raw, payload, schema)
        result.setdefault("product_id", product_id)
        result["period"] = payload["period"]
        result["fallback"] = False
        return result
    except Exception as e:              # 어떤 실패든 폴백 (🔴 에러를 던지면 시연이 멈춤)
        return _fallback(str(e) if isinstance(e, AIFailed) else type(e).__name__)
