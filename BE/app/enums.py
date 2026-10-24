"""열거형 코드 ↔ 한글 라벨 (CONVENTIONS §9).

진짜 기준은 DATA/enums.json 입니다. 이 파일은 그것을 읽기만 합니다.
- 저장·전송은 영문 코드, 화면 표시는 한글 라벨
- 주문 CSV의 한글 라벨(source_label)은 영문 코드로 바꿔서 저장

※ enums.json 의 정확한 구조를 아직 못 봤기 때문에, 흔한 구조 몇 가지를
  모두 읽을 수 있게 만들었습니다. enums.json 이 없으면 아래 BUILTIN 값을 씁니다.
  BUILTIN 은 api.md 예시에서 확인된 값만 넣었고, 나머지는 enums.json 이 정답입니다.
"""
import json
from functools import lru_cache

from app.config import ENUMS_JSON

# api.md 예시에 나온 값들 (enums.json 이 없을 때만 사용)
BUILTIN = {
    "return_types": [
        {"code": "SIZE_FIT", "label": "사이즈·핏 문제"},
        {"code": "CHANGE_OF_MIND", "label": "단순 변심"},
        {"code": "QUALITY_FINISH", "label": "봉제·마감 불만", "source_label": ["바느질/마감"]},
        {"code": "COLOR_IMAGE", "label": "색상·이미지 차이"},
        {"code": "SHIPPING", "label": "배송·포장"},
        {"code": "OTHER", "label": "기타·판단 불확실"},
        {"code": "FABRIC_FEEL", "label": "원단·촉감·두께"},
        {"code": "DEFECTIVE", "label": "불량 제품", "source_label": ["불량 제품"]},
    ],
    "defect_types": [
        {"code": "SEWING", "label": "봉제·재봉"},
        {"code": "FABRIC", "label": "원단·소재 결함"},
        {"code": "FINISH", "label": "외관·마감"},
    ],
    "task_types": [
        {"code": "PRODUCT_FIX", "label": "실제 상품 수정"},
    ],
    "task_statuses": [
        {"code": "PENDING", "label": "대기"},
        {"code": "IN_PROGRESS", "label": "진행 중"},   # 라벨은 enums.json 확인 필요
        {"code": "DONE", "label": "완료"},             # 코드·라벨 enums.json 확인 필요
    ],
}

# enums.json 안에서 그룹 이름이 무엇일지 후보를 둡니다.
GROUP_ALIASES = {
    # 앞쪽이 실제 DATA/enums.json 의 그룹 이름입니다
    "return_types": ["return_reasons", "return_types"],
    "defect_types": ["defect_types"],
    "task_types": ["checklist_type", "task_types"],
    "task_statuses": ["task_status", "task_statuses"],
    "task_sources": ["task_source"],
    "inventory_status": ["inventory_status"],
    "channels": ["sales_channels", "channels"],
}


def _normalize(value) -> list[dict] | None:
    """그룹 하나를 [{"code", "label", "source_labels": [...]}, ...] 로 맞춥니다."""
    items = []
    if isinstance(value, list):
        for v in value:
            if isinstance(v, dict) and "code" in v:
                items.append(v)
            elif isinstance(v, str):
                items.append({"code": v, "label": v})
    elif isinstance(value, dict):            # {"SEWING": "봉제·재봉"} 또는 {"SEWING": {...}}
        for code, v in value.items():
            if isinstance(v, dict):
                items.append({"code": code, **v})
            else:
                items.append({"code": code, "label": str(v)})
    else:
        return None

    result = []
    for it in items:
        src = it.get("source_label", it.get("source_labels", []))
        if isinstance(src, str):
            src = [src]
        result.append({"code": it["code"], "label": it.get("label", it["code"]), "source_labels": list(src)})
    return result or None


@lru_cache
def load() -> dict:
    data = {}
    if ENUMS_JSON.exists():
        try:
            data = json.loads(ENUMS_JSON.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}

    groups = {}
    for name, aliases in GROUP_ALIASES.items():
        found = None
        for key in aliases:
            if isinstance(data, dict) and key in data:
                found = _normalize(data[key])
                if found:
                    break
        if not found and name in BUILTIN:
            found = _normalize(BUILTIN[name])
        groups[name] = found or []
    return groups


def codes(group: str) -> set[str]:
    return {it["code"] for it in load()[group]}


def label(group: str, code: str | None) -> str | None:
    for it in load()[group]:
        if it["code"] == code:
            return it["label"]
    return None


def to_code(group: str, text: str | None) -> str | None:
    """영문 코드, 한글 라벨, source_label 중 무엇이 와도 영문 코드로 바꿉니다. 못 찾으면 None."""
    if text is None:
        return None
    t = text.strip()
    for it in load()[group]:
        if t == it["code"] or t == it["label"] or t in it["source_labels"]:
            return it["code"]
    return None
