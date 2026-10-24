"""FashionERP AI output verification tests. Run from repository root:

    python -m unittest discover -s AI/tests -p test_output_verification.py -v

Reuses the existing AI/prompts/run_analysis.py::verify() without copying it.
Does not call an LLM or require .env.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "AI" / "prompts"))

from build_input import build  # noqa: E402
from run_analysis import verify  # noqa: E402


OTHER_PRODUCTS = ("P001", "P003", "P004", "P005", "P006", "P008")
PRODUCTS = ("P001", "P002", "P003", "P004", "P005", "P006", "P007", "P008")


def sample_output(product_id: str):
    """Build a synthetic, consistent output from the actual source dataset.

    This is a *test fixture*, not an LLM classification result. The categories
    here summarize customer-selected reasons, not AI classifications.
    """
    payload = build(product_id)
    with (ROOT / "DATA" / "enums.json").open(encoding="utf-8") as file:
        enums = json.load(file)
    reason_by_label = {e["source_label"]: e for e in enums["return_reasons"]}

    rc = payload["stats"]["return_count"]
    categories = []
    for selected in payload["selected_reasons"]:
        reason = reason_by_label[selected["source_label"]]
        count = selected["count"]
        categories.append(
            {
                "code": reason["code"],
                "label": reason["label"],
                "count": count,
                "share_pct": round(count / rc * 100, 1) if rc else 0.0,
            }
        )

    issue_count = sum(
        c["count"]
        for c in categories
        if c["code"] not in ("CHANGE_OF_MIND", "OTHER")
    )
    insufficient = rc < 10 or issue_count < 5

    facts = []
    if payload["returns"]:
        first = payload["returns"][0]
        ids = first.get("order_ids") or ([first["order_id"]] if "order_id" in first else [])
        if ids:
            facts.append(
                {
                    "statement": "입력된 반품 의견 중 다음 고객 의견이 존재합니다.",
                    "evidence_quotes": [first["text"]],
                    "evidence_order_ids": [ids[0]],
                }
            )

    output = {
        "product_id": product_id,
        "period": payload["period"],
        "analyzed_count": rc,
        "categories": categories,
        "observed_facts": facts,
        "possible_causes": [],
        "checks_needed": [],
        "improvement_checklist": [],
        "insufficient_data": insufficient,
        "fallback": False,
        "notes": (
            [{"code": "SMALL_SAMPLE", "message": "검토 가능한 반품 사례가 충분하지 않습니다."}]
            if insufficient
            else []
        ),
    }
    return output, payload


def assert_error(testcase: unittest.TestCase, output: dict, payload: dict, keyword: str):
    errors = verify(output, payload)
    testcase.assertTrue(
        any(keyword in error for error in errors),
        msg=f"Expected error containing {keyword!r}; got: {errors!r}",
    )


def source_case(sentence: str):
    """Find a real source row for an exception-evidence test, not an AI label."""
    for product_id in PRODUCTS:
        payload = build(product_id)
        for item in payload["returns"]:
            if item["text"] == sentence:
                return product_id, payload, item
    raise AssertionError(f"Sentence not found in the source CSV: {sentence!r}")


class OutputVerificationTests(unittest.TestCase):
    def setUp(self):
        self.out, self.payload = sample_output("P002")

    def test_p002_existing_fallback(self):
        with (ROOT / "AI" / "fallback" / "returns-analyze.json").open(encoding="utf-8") as f:
            fallback = json.load(f)
        self.assertTrue(fallback["fallback"])
        self.assertEqual(fallback["product_id"], "P002")
        self.assertEqual(verify(fallback, self.payload), [])

    def test_p002_fallback_full_json_schema(self):
        # jsonschema 는 선택 의존성(AI/requirements.txt). 없으면 실패가 아니라 skip 한다.
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema 미설치: pip install -r AI/requirements.txt")

        with (ROOT / "AI" / "schemas" / "return-analysis.schema.json").open(encoding="utf-8") as f:
            schema = json.load(f)
        with (ROOT / "AI" / "fallback" / "returns-analyze.json").open(encoding="utf-8") as f:
            fallback = json.load(f)
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(fallback), key=lambda e: str(e.path))
        self.assertEqual([e.message for e in errors], [])

    def test_remaining_six_products_data_driven(self):
        for product_id in OTHER_PRODUCTS:
            with self.subTest(product_id=product_id):
                output, payload = sample_output(product_id)
                self.assertEqual(verify(output, payload), [])
                self.assertEqual(output["analyzed_count"], payload["stats"]["return_count"])

    def test_all_eight_return_types_in_source_and_validation_fixture(self):
        with (ROOT / "DATA" / "enums.json").open(encoding="utf-8") as file:
            enums = json.load(file)
        reason_by_label = {e["source_label"]: e for e in enums["return_reasons"]}
        payload = build("P002")
        source_labels = {reason["source_label"] for reason in payload["selected_reasons"]}
        output, _ = sample_output("P002")

        self.assertEqual(source_labels, set(reason_by_label))
        self.assertEqual(
            {category["code"] for category in output["categories"]},
            {reason["code"] for reason in enums["return_reasons"]},
        )
        self.assertEqual(verify(output, payload), [])

    def test_exception_sentences_are_exact_source_evidence(self):
        exception_sentences = (
            "생각보다 품이 너무 크고 기장도 어정쩡해요",
            "선물하려고 했는데 일정이 취소되었어요",
            "기타 사유로 인한 반품 요청입니다",
        )
        for sentence in exception_sentences:
            with self.subTest(sentence=sentence):
                product_id, payload, source_item = source_case(sentence)
                output, _ = sample_output(product_id)
                output["observed_facts"] = [
                    {
                        "statement": "원본 CSV 문장을 그대로 인용한 검증 fixture입니다.",
                        "evidence_quotes": [source_item["text"]],
                        "evidence_order_ids": [source_item["order_ids"][0]],
                    }
                ]

                self.assertEqual(verify(output, payload), [])

    def test_p007_insufficient_data(self):
        output, payload = sample_output("P007")
        self.assertTrue(output["insufficient_data"], "P007 is the repository small-sample example")
        self.assertEqual(verify(output, payload), [])

    def test_empty_evidence_quotes_rejected(self):
        self.out["observed_facts"][0]["evidence_quotes"] = []
        assert_error(self, self.out, self.payload, "evidence_quotes 가 비어 있음")

    def test_empty_evidence_order_ids_rejected(self):
        self.out["observed_facts"][0]["evidence_order_ids"] = []
        assert_error(self, self.out, self.payload, "evidence_order_ids 가 비어 있음")

    def test_both_evidence_lists_empty_rejected(self):
        self.out["observed_facts"][0]["evidence_quotes"] = []
        self.out["observed_facts"][0]["evidence_order_ids"] = []
        errors = verify(self.out, self.payload)
        self.assertTrue(any("evidence_quotes 가 비어 있음" in e for e in errors), errors)
        self.assertTrue(any("evidence_order_ids 가 비어 있음" in e for e in errors), errors)

    def test_hallucinated_quote_rejected(self):
        self.out["observed_facts"][0]["evidence_quotes"] = ["원본 데이터에 존재하지 않는 테스트 문장"]
        assert_error(self, self.out, self.payload, "환각 인용")

    def test_unknown_order_id_rejected(self):
        self.out["observed_facts"][0]["evidence_order_ids"] = ["P002-INVALID-ID"]
        assert_error(self, self.out, self.payload, "없는 order_id")

    def test_category_count_sum_rejected(self):
        self.out["categories"][0]["count"] += 1
        assert_error(self, self.out, self.payload, "categories 합")

    def test_unknown_category_rejected(self):
        self.out["categories"][0]["code"] = "FAKE_CATEGORY"
        assert_error(self, self.out, self.payload, "미등록 코드")

    def test_category_label_rejected(self):
        self.out["categories"][0]["label"] = "잘못된 라벨"
        assert_error(self, self.out, self.payload, "label 불일치")

    def test_share_percentage_range_rejected(self):
        self.out["categories"][0]["share_pct"] = 120.0
        assert_error(self, self.out, self.payload, "share_pct 범위 밖")

    def test_reverse_insufficient_data_low_return_count(self):
        # P007 has fewer than 10 returned orders in the dataset.
        output, payload = sample_output("P007")
        output["insufficient_data"] = False
        assert_error(self, output, payload, "insufficient_data 가 false 인데 반품")

    def test_reverse_insufficient_data_few_product_issues(self):
        # Preserve the overall return count while reducing product-related issues.
        out = copy.deepcopy(self.out)
        total = out["analyzed_count"]
        for category in out["categories"]:
            category["count"] = total if category["code"] == "CHANGE_OF_MIND" else 0
            category["share_pct"] = 100.0 if category["code"] == "CHANGE_OF_MIND" else 0.0
        out["insufficient_data"] = False
        assert_error(self, out, self.payload, "insufficient_data 가 false 인데 상품 문제 반품")

    def test_insufficient_true_with_causes_rejected(self):
        out, payload = sample_output("P007")
        out["possible_causes"] = [{"statement": "원인일 가능성이 있습니다.", "confidence": "LOW"}]
        assert_error(self, out, payload, "possible_causes 가 비어 있지 않음")


if __name__ == "__main__":
    unittest.main()
