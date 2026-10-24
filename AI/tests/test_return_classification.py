"""Live LLM classification checks against source-selected return reasons.

Run with:
    python -m unittest discover -s AI/tests -p test_return_classification.py -v

The test makes one API call for eight representative reasons and four edge cases
when LLM_API_KEY is configured in the environment or repository .env file.
"""

from __future__ import annotations

import collections
import csv
import json
import os
import pathlib
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets" / "product_return_dataset_2000.csv"
ENUMS = ROOT / "DATA" / "enums.json"
DEFAULT_MODEL = "gemini-3.8-flash"

EDGE_SENTENCES = (
    ("edge-contradictory-fit", "생각보다 품이 너무 크고 기장도 어정쩡해요"),
    ("edge-cancelled-gift", "선물하려고 했는데 일정이 취소되었어요"),
    ("edge-unspecified-reason", "기타 사유로 인한 반품 요청입니다"),
    ("edge-vague-expectation", "실물을 보니 생각했던 느낌이 아니네요"),
)


def api_settings():
    settings = {}
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip().strip('"').strip("'")

    api_key = os.environ.get("LLM_API_KEY") or settings.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL") or settings.get("LLM_MODEL") or DEFAULT_MODEL
    if not api_key:
        return None
    return api_key, model


def load_source_cases():
    with ENUMS.open(encoding="utf-8") as file:
        reasons = json.load(file)["return_reasons"]
    code_by_source_label = {
        reason["source_label"]: reason["code"] for reason in reasons
    }
    with DATASET.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    returned = [
        row for row in rows
        if row["is_returned"] == "1" and row["return_type_code"] in code_by_source_label
    ]
    cases = []
    for reason in reasons:
        matching_texts = collections.Counter(
            row["return_detail_text"].strip("'")
            for row in returned
            if row["return_type_code"] == reason["source_label"]
        )
        if not matching_texts:
            raise AssertionError(f"No source rows for category {reason['code']}")
        text, _ = matching_texts.most_common(1)[0]
        cases.append(
            {
                "case_id": f"category-{reason['code'].lower()}",
                "expected_code": reason["code"],
                "text": text,
            }
        )

    for case_id, text in EDGE_SENTENCES:
        matches = {
            code_by_source_label[row["return_type_code"]]
            for row in returned
            if row["return_detail_text"].strip("'") == text
        }
        if len(matches) != 1:
            raise AssertionError(
                f"Expected one source-selected reason for {case_id}, got {sorted(matches)}"
            )
        cases.append(
            {
                "case_id": case_id,
                "expected_code": matches.pop(),
                "text": text,
            }
        )
    return cases, [reason["code"] for reason in reasons], [reason["label"] for reason in reasons]


def classify_with_gemini(api_key, model, cases, codes, labels):
    taxonomy = [
        {"code": code, "label": label}
        for code, label in zip(codes, labels)
    ]
    system_prompt = (
        "당신은 패션 상품 반품 자유서술 문장을 분류합니다. 각 문장을 제공된 "
        "반품 유형 중 하나로 분류하세요. 고객이 실제로 말한 사유만 판단하고, "
        "구체적 근거가 없거나 분류할 수 없으면 OTHER를 선택하세요. "
        "주문별 예상 정답이나 설명은 출력하지 말고, 요청한 JSON 형식만 반환하세요."
    )
    user_prompt = {
        "categories": taxonomy,
        "cases": [
            {"case_id": case["case_id"], "text": case["text"]}
            for case in cases
        ],
        "response_format": {
            "classifications": [{"case_id": "입력 case_id", "code": "분류 코드"}]
        },
    }
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(user_prompt, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


class LiveReturnClassificationTests(unittest.TestCase):
    def test_source_sentences_match_live_llm_classifications(self):
        settings = api_settings()
        if settings is None:
            self.skipTest("LLM_API_KEY 미설정: 실제 LLM 분류 미실행")

        api_key, model = settings
        cases, codes, labels = load_source_cases()
        try:
            result = classify_with_gemini(api_key, model, cases, codes, labels)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 404, 429, 500, 503):
                self.skipTest(f"LLM API 호출 불가 (HTTP {error.code}): 분류 미실행")
            raise
        except (urllib.error.URLError, TimeoutError):
            self.skipTest("LLM API 네트워크 연결 불가: 분류 미실행")

        classifications = result["classifications"]
        actual_by_id = {
            item["case_id"]: item["code"]
            for item in classifications
        }
        expected_ids = {case["case_id"] for case in cases}
        self.assertEqual(len(classifications), len(cases), "분류 결과 수가 입력 케이스와 다릅니다")
        self.assertEqual(set(actual_by_id), expected_ids, "분류 결과의 case_id가 입력과 다릅니다")
        self.assertTrue(
            set(actual_by_id.values()).issubset(set(codes)),
            f"등록되지 않은 분류 코드가 있습니다: {actual_by_id}",
        )

        mismatches = []
        for case in cases:
            actual = actual_by_id[case["case_id"]]
            status = "오분류" if actual != case["expected_code"] else "일치"
            print(
                f"{case['case_id']}: expected={case['expected_code']} "
                f"actual={actual} result={status}"
            )
            if actual != case["expected_code"]:
                mismatches.append(
                    f"{case['case_id']} expected={case['expected_code']} actual={actual}"
                )
        self.assertEqual(mismatches, [], "원본 CSV 예상 사유와 실제 LLM 분류가 다릅니다")


if __name__ == "__main__":
    unittest.main()
