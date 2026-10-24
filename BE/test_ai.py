"""AI 분석: 실제 Gemini 대신 가짜 호출 함수로 성공·검사·폴백 흐름을 확인합니다 (비용 0원)."""
import copy
import io
import json
import urllib.error

import pytest

from app.config import REPO_DIR
from app.database import connect, init_db
from app.importers.loader import seed_if_empty
from app.services import ai

SAMPLE = REPO_DIR / "AI" / "prompts" / "sample-output-P002.json"
FULL = {"from": "2026-01-10", "to": "2026-10-24"}


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()


def sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_payload_matches_reference_structure(conn):
    p = ai.build_payload(conn, "P002", FULL)
    assert p["stats"] == {"order_count": 277, "return_count": 57, "return_rate_pct": 20.6}
    assert sum(r["count"] for r in p["returns"]) == 57 and len(p["returns"]) == 14   # 57건 → 14그룹
    assert {"source_label": "사이즈/핏", "count": 22} in p["selected_reasons"]           # 한글 원본 값으로 전송
    assert p["defect_context_note"]                                                    # 발주 3건 불량 10장


def test_gemini_schema_drops_unsupported_keys():
    schema = json.loads(ai.SCHEMA_JSON.read_text(encoding="utf-8"))
    text = json.dumps(ai.to_gemini_schema(schema))
    for bad in ("additionalProperties", "$schema", "$id", "pattern", "minLength"):
        assert bad not in text


def test_success_with_fake_llm(conn):
    out = ai.analyze_returns(conn, "P002", FULL, caller=lambda *a: sample())
    assert out["fallback"] is False and out["analyzed_count"] == 57
    assert out["observed_facts"]                                                       # 근거 있는 사실은 유지


def test_label_is_overwritten_from_enums(conn):
    bad = sample(); bad["categories"][0]["label"] = "사이즈/핏"                          # 모델이 한글 원본을 보낸 경우
    out = ai.analyze_returns(conn, "P002", FULL, caller=lambda *a: bad)
    assert out["categories"][0]["label"] == "사이즈·핏 문제"


def test_fact_without_evidence_is_removed(conn):
    bad = sample(); bad["observed_facts"][0]["evidence_quotes"] = []                   # minItems 무시된 경우
    n = len(bad["observed_facts"])
    out = ai.analyze_returns(conn, "P002", FULL, caller=lambda *a: copy.deepcopy(bad))
    assert len(out["observed_facts"]) == n - 1
    assert any(x["code"] == "AI_UNCERTAIN" for x in out["notes"])


def test_broken_output_falls_back(conn):
    bad = sample(); bad["analyzed_count"] = 999
    out = ai.analyze_returns(conn, "P002", FULL, caller=lambda *a: bad)
    assert out["fallback"] is True


def test_exception_falls_back(conn):
    def boom(*a):
        raise RuntimeError("x")
    assert ai.analyze_returns(conn, "P002", FULL, caller=boom)["fallback"] is True


def test_no_key_falls_back(conn):
    assert ai.analyze_returns(conn, "P002", FULL)["fallback"] is True


def test_retry_503_then_success(monkeypatch):
    calls, waits = [], []
    good = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": 1})}]}}]}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b""))
        return Resp(json.dumps(good).encode())

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ai, "_sleep", waits.append)
    assert ai.call_gemini("k", "m", "s", {}, {}) == {"ok": 1}
    assert waits == [5, 10] and calls == [180, 180, 180]


def test_400_fails_immediately(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b""))

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ai.AIFailed):
        ai.call_gemini("k", "m", "s", {}, {})
    assert len(calls) == 1
