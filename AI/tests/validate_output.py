"""FashionERP: AI 반품 분석 결과 검증기.

저장 위치: FashionERP/AI/tests/validate_output.py
실행: python AI/tests/validate_output.py
다른 AI 결과: python AI/tests/validate_output.py --output AI/tests/llm_result.json
필요 패키지: pip install jsonschema

주의: 수치, 코드, 주문-ID와 인용의 원본 일치 여부를 자동 검증합니다.
자유 서술 문장의 모든 의미적 주장까지 자동 입증하는 것은 불가능합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("[오류] jsonschema가 없습니다. 실행: python -m pip install jsonschema")
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[2]  # AI/tests -> FashionERP
DEFAULT_OUTPUT = ROOT / "AI/fallback/returns-analyze.json"
DEFAULT_SCHEMA = ROOT / "AI/schemas/return-analysis.schema.json"
DEFAULT_DATASET = ROOT / "datasets/product_return_dataset_2000.csv"
DEFAULT_ENUMS = ROOT / "DATA/enums.json"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    required = {"date", "product_id", "order_id", "is_returned", "return_type_code",
                "return_detail_text", "size", "color"}
    if not rows:
        raise ValueError("원본 CSV가 비어 있습니다")
    missing = required - rows[0].keys()
    if missing:
        raise ValueError(f"원본 CSV 필수 열 누락: {', '.join(sorted(missing))}")
    return rows


def normalize_quote(text: str | None) -> str:
    """원본 CSV 텍스트의 양끝 작은따옴표만 제거. 내부 문자열은 수정하지 않음."""
    text = (text or "").strip()
    if len(text) >= 2 and text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return text


def pct(count: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.0")
    return (Decimal(count) * 100 / Decimal(denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def close_pct(value: Any, expected: Decimal) -> bool:
    try:
        return abs(Decimal(str(value)) - expected) <= Decimal("0.00001")
    except (ValueError, TypeError, ArithmeticError):
        return False


def check_response(
    output: dict[str, Any],
    schema: dict[str, Any],
    rows: list[dict[str, str]],
    enums: dict[str, Any],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    # 1) JSON 스키마: 필수 키/자료형/허용값/추가 키
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(output), key=lambda e: str(list(e.absolute_path))):
        where = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"[스키마] {where}: {error.message}")
    if not isinstance(output, dict):
        return errors, warnings

    # 스키마가 깨진 결과도 검사를 지속하면 프로그램 에러가 나므로 여기서 종료
    if errors:
        return errors, warnings

    product_id = output["product_id"]
    period = output.get("period")
    lower, upper = None, None
    if period is not None:
        try:
            lower = date.fromisoformat(period["from"])
            upper = date.fromisoformat(period["to"])
            if lower > upper:
                errors.append("[기간] period.from이 period.to보다 늦습니다")
        except ValueError:
            errors.append("[기간] 존재하지 않는 날짜입니다")

    filtered = [
        row for row in rows
        if row["product_id"] == product_id
        and row["is_returned"].strip() == "1"
        and (lower is None or lower.isoformat() <= row["date"] <= upper.isoformat())
    ]
    # 같은 order_id가 중복되면 근거 매칭 자체를 신뢰할 수 없다.
    ids = [row["order_id"] for row in filtered]
    if len(ids) != len(set(ids)):
        errors.append("[데이터] 분석 범위에 중복 order_id가 있습니다")
    by_id = {row["order_id"]: row for row in filtered}
    total = len(filtered)

    # 2) 분석 범위와 건수
    if output["analyzed_count"] != total:
        errors.append(
            f"[건수] analyzed_count={output['analyzed_count']} / 원본 반품={total}건 "
            "(상품·기간·is_returned=1 조건)"
        )

    # 3) 코드/라벨, 중복, 비율, 합계
    mappings = {item["code"]: item for item in enums["return_reasons"]}
    categories = output["categories"]
    code_list = [x["code"] for x in categories]
    if len(code_list) != len(set(code_list)):
        errors.append("[분류] categories에 중복 code가 있습니다")

    if sum(x["count"] for x in categories) != output["analyzed_count"]:
        errors.append("[분류] categories[].count의 합과 analyzed_count가 다릅니다")

    expected_source = Counter(row["return_type_code"].strip() for row in filtered)
    for i, item in enumerate(categories):
        code = item["code"]
        conf = mappings.get(code)
        if conf is None:
            errors.append(f"[분류] categories[{i}].code={code}는 DATA/enums.json에 없습니다")
        elif item["label"] != conf["label"]:
            errors.append(f"[분류] {code}의 label이 DATA/enums.json과 다릅니다")
        if not close_pct(item["share_pct"], pct(item["count"], output["analyzed_count"])):
            errors.append(f"[비율] categories[{i}] {code}: count와 share_pct 불일치")

        # 폴백 데이터의 categories는 '고객이 직접 선택한 반품 사유' 집계.
        # 실제 LLM 분류는 고객 선택값과 다를 수 있으므로 이 대조를 강제하지 않음.
        if output["fallback"] and conf is not None:
            actual = expected_source[conf["source_label"]]
            if item["count"] != actual:
                errors.append(
                    f"[원본 집계] {code}: JSON {item['count']}건 / CSV {actual}건"
                )

    if output["fallback"]:
        unlisted = sorted(set(mappings) - set(code_list))
        if any(expected_source[mappings[code]["source_label"]] for code in unlisted):
            errors.append("[원본 집계] 원본 반품이 있는 분류 코드가 categories에서 빠졌습니다")

    # 4) order_id와 고객 발언을 동일 원본 행에서 쌍으로 검증
    for i, fact in enumerate(output["observed_facts"]):
        quote_list = fact["evidence_quotes"]
        order_list = fact["evidence_order_ids"]
        if len(quote_list) != len(order_list):
            errors.append(f"[근거] observed_facts[{i}]: 인용문·주문번호 개수가 달라 일대일 대응 불가")
            continue
        for j, (quote, order_id) in enumerate(zip(quote_list, order_list)):
            row = by_id.get(order_id)
            if row is None:
                errors.append(
                    f"[주문번호] observed_facts[{i}].evidence_order_ids[{j}] "
                    f"{order_id}: 분석 상품·기간의 반품 원본에 없음"
                )
            elif quote != normalize_quote(row["return_detail_text"]):
                errors.append(
                    f"[원문] observed_facts[{i}].evidence_quotes[{j}]: "
                    f"{order_id}의 return_detail_text와 정확히 일치하지 않음"
                )

        # 자주 등장하는 '57건 중 22건(38.6%)' 형식의 수치 주장도 실제 집계와 대조
        for denominator, count, ratio in re.findall(
            r"(\d+)건\s*중\s*(\d+)건\s*\((\d+(?:\.\d+)?)%\)",
            fact["statement"],
        ):
            if int(denominator) != total:
                errors.append(f"[사실] observed_facts[{i}]: 반품 전체 건수 {denominator}가 원본과 다름")
            valid_pair = any(
                c["count"] == int(count)
                and close_pct(ratio, pct(c["count"], total))
                for c in categories
            )
            if not valid_pair:
                errors.append(f"[사실] observed_facts[{i}]: {count}건({ratio}%)의 집계 근거가 없음")

    # 5) 사이즈 / 색상별 반품 건수 (전체 주문 대비 반품률과 혼동하지 않음)
    found_dimensions = set()
    for i, item in enumerate(output.get("size_color_findings", [])):
        dim, value = item["dimension"], item["value"]
        key = (dim, value)
        if key in found_dimensions:
            errors.append(f"[차원] size_color_findings[{i}] 중복: {dim}={value}")
        found_dimensions.add(key)
        actual = sum(row[dim] == value for row in filtered)
        if item["count"] != actual:
            errors.append(f"[차원] {dim}={value}: JSON {item['count']}건 / 원본 {actual}건")
        if not close_pct(item["share_pct"], pct(item["count"], total)):
            errors.append(f"[차원] {dim}={value}: count와 share_pct 불일치")

    # 6) 빈 데이터 / 폴백 상태 / 원인 표현 검토
    note_codes = [n["code"] for n in output.get("notes", [])]
    allowed_notes = {n["code"] for n in enums["note_codes"]}
    for code in note_codes:
        if code not in allowed_notes:
            errors.append(f"[메모] {code}: DATA/enums.json에 정의되지 않은 코드")

    if output["insufficient_data"]:
        if output["possible_causes"]:
            errors.append("[데이터 부족] insufficient_data=true인데 possible_causes가 비어 있지 않음")
        if "AI_UNCERTAIN" not in note_codes:
            errors.append("[데이터 부족] notes에 AI_UNCERTAIN이 필요함")
    if total == 0 and not output["insufficient_data"]:
        errors.append("[데이터 부족] 반품 데이터가 0건인데 insufficient_data=false")

    if output["fallback"] and (not note_codes or note_codes[0] != "AI_FALLBACK"):
        errors.append("[폴백] fallback=true면 notes[0].code가 AI_FALLBACK이어야 함")
    if not output["fallback"] and "AI_FALLBACK" in note_codes:
        errors.append("[폴백] fallback=false인데 AI_FALLBACK 메모가 있음")

    for i, cause in enumerate(output["possible_causes"]):
        statement = cause["statement"].strip()
        if re.search(r"(원인이다|때문이다|확정됐다|확실하다)", statement):
            errors.append(f"[단정] possible_causes[{i}]에서 추정 원인을 확정적으로 표현함")
        if not any(token in statement for token in ("가능성", "추정", "보입니다", "수 있습니다", "의심")):
            warnings.append(f"possible_causes[{i}]: 추정임이 드러나도록 표현을 수동 검토하세요")

    warnings.append(
        "observed_facts의 자연어 의미, 가능한 원인의 타당성, 개선 조치의 적절성은 "
        "인간 검토가 추가로 필요합니다 (문자열/산술 검사만으로 완전 검증 불가)."
    )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="FashionERP AI 출력 JSON 구조 및 근거 검증")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="검증할 AI 출력 JSON")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--enums", type=Path, default=DEFAULT_ENUMS)
    args = parser.parse_args()

    try:
        output = read_json(args.output)
        schema = read_json(args.schema)
        rows = read_csv(args.dataset)
        enums = read_json(args.enums)
        Draft202012Validator.check_schema(schema)
        errors, warnings = check_response(output, schema, rows, enums)
    except (OSError, ValueError, csv.Error, KeyError, TypeError) as exc:
        print(f"[FAIL] 파일 또는 입력 데이터 오류: {exc}")
        return 1
    except Exception as exc:
        print(f"[FAIL] 검증기 오류: {type(exc).__name__}: {exc}")
        return 1

    for error in errors:
        print(f"[FAIL] {error}")
    for warning in warnings:
        print(f"[검토 필요] {warning}")
    if errors:
        print(f"\n검증 실패: 오류 {len(errors)}개 / 검토 알림 {len(warnings)}개")
        return 1
    print(f"\n[PASS] 자동 출력 검증 통과 / 검토 알림 {len(warnings)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
