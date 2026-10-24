"""리뷰 키워드 자동 분류 (api.md: GET /api/returns/review-keywords).

입력: 이미 적재된 반품 리뷰 문장 (returns.return_detail_text — 주문 CSV 의 return_detail_text,
      적재 때 따옴표 제거·"NA" → NULL 처리가 끝난 값). 새 데이터를 만들거나 바꾸지 않습니다.

방법: 규칙 기반 키워드 사전. AI 를 쓰지 않으므로 같은 입력이면 항상 같은 결과입니다.
      사전의 키워드는 실제 리뷰 문장 17종에 나온 표현을 근거로 정했습니다.

집계 기준
  - 한 리뷰에서 여러 분류의 키워드가 나오면 **각 분류에 1건씩** 셉니다 (다중 분류).
  - 같은 리뷰에서 같은 키워드가 여러 번 나와도 1번으로 셉니다.
  - 분류 비율(%) = 그 분류에 들어간 리뷰 수 ÷ 분석한 리뷰 수 × 100
    → 다중 분류 때문에 비율 합계가 100%를 넘을 수 있습니다.
  - 어떤 키워드도 없거나 원인을 말하지 않는 리뷰("기타 사유로 …")는 억지로 나누지 않고 UNCLASSIFIED.
"""
import re
import sqlite3

from app.utils import note, pct

# (코드, 화면 라벨, 키워드 목록)  ← 키워드는 리뷰 원문에 그대로 들어 있어야 매칭됩니다
CATEGORIES = [
    ("SIZE_FIT", "사이즈·핏", ["사이즈", "작게", "크게", "타이트", "헐렁", "기장", "품이", "허리", "골반", "어깨"]),
    ("QUALITY", "품질·마감", ["실밥", "마감", "올이 풀", "오염", "지퍼", "뻑뻑", "잠기지 않", "단추", "구멍", "불량"]),
    ("FABRIC", "소재·원단", ["원단", "소재", "얇아", "두꺼", "까끌", "보풀", "비침"]),
    ("COLOR", "색상·이미지 차이", ["색감", "화면보다", "사진과", "어두운", "밝은", "색이 달"]),
    ("DESIGN", "디자인·실물 느낌", ["실물", "느낌이 아니", "디자인", "핏감", "스타일"]),
    ("SHIPPING", "배송·포장", ["배송", "늦어", "박스", "포장", "찌그러", "패키지", "파손", "손상"]),
    ("CHANGE_OF_MIND", "단순 변심·개인 사정", ["선물", "일정", "다른 색상", "더 나을 것 같", "마음이 바뀌"]),
]
UNCLASSIFIED = ("UNCLASSIFIED", "분류 불가")
LABEL = {c: l for c, l, _ in CATEGORIES} | {UNCLASSIFIED[0]: UNCLASSIFIED[1]}

# "기타 사유로 인한 반품" 처럼 원인을 말하지 않는 문장은 키워드가 우연히 걸려도 분류하지 않습니다
NO_CAUSE = re.compile(r"^기타 사유")
SMALL_SAMPLE_REVIEWS = 10      # 반품률과 같은 기준 (CONVENTIONS §7)
LOW_VARIETY_RATIO = 0.3        # 서로 다른 문장 ÷ 리뷰 수 가 이보다 작으면 키워드 다양성이 낮다고 표시


def classify(text: str | None) -> dict[str, list[str]]:
    """리뷰 한 건 → {분류 코드: [찾은 키워드, ...]}. 원인이 없으면 {"UNCLASSIFIED": []}"""
    t = (text or "").strip()
    if not t or NO_CAUSE.search(t):
        return {UNCLASSIFIED[0]: []}
    found = {}
    for code, _, words in CATEGORIES:
        hits = [w for w in words if w in t]
        if hits:
            found[code] = hits
    return found or {UNCLASSIFIED[0]: []}


def analyze_texts(rows: list[dict]) -> dict:
    """rows = [{"order_id", "product_id", "text", "reason_code"}, ...] → 집계 결과 (DB 없이 테스트 가능)"""
    n = len(rows)
    cat_reviews = {code: 0 for code in LABEL}
    kw_count: dict[tuple[str, str], int] = {}
    example: dict[str, dict] = {}
    for r in rows:
        found = classify(r["text"])
        for code, hits in found.items():
            cat_reviews[code] += 1
            example.setdefault(code, r)
            for w in hits:
                kw_count[(w, code)] = kw_count.get((w, code), 0) + 1

    # 화면 왼쪽 카드에 보여줄 실제 리뷰 1건: 가장 많은 분류에 속한 리뷰 중 키워드가 가장 많은 것 (같으면 먼저 나온 것)
    best = None
    for r in rows:
        found = classify(r["text"])
        if UNCLASSIFIED[0] in found:
            continue
        key = (max(cat_reviews[c] for c in found), sum(len(h) for h in found.values()))
        if best is None or key > best[0]:
            best = (key, r, found)

    categories = []
    for code in [c for c, _, _ in CATEGORIES] + [UNCLASSIFIED[0]]:
        cnt = cat_reviews[code]
        if not cnt:
            continue
        kws = sorted(((w, c) for (w, cc), c in kw_count.items() if cc == code), key=lambda x: -x[1])
        ex = example[code]
        categories.append({
            "code": code, "label": LABEL[code], "count": cnt, "share_pct": pct(cnt, n),
            "keywords": [{"keyword": w, "count": c} for w, c in kws],
            "example": {"order_id": ex["order_id"], "product_id": ex["product_id"], "text": ex["text"]},
        })
    categories.sort(key=lambda x: (x["code"] == UNCLASSIFIED[0], -x["count"]))   # 많은 순, 분류 불가는 맨 뒤

    top_keywords = [{"keyword": w, "category": code, "category_label": LABEL[code], "count": c,
                     "share_pct": pct(c, n)}
                    for (w, code), c in sorted(kw_count.items(), key=lambda kv: -kv[1])]

    # 고객이 고른 반품 사유(return_type_code)와 리뷰 문장 분류가 어떻게 겹치는지 (검증·인사이트용)
    cross: dict[tuple[str, str], int] = {}
    for r in rows:
        for code in classify(r["text"]):
            key = (r.get("reason_code") or "OTHER", code)
            cross[key] = cross.get(key, 0) + 1

    unique = len({r["text"] for r in rows})
    multi = sum(1 for r in rows if len(classify(r["text"])) > 1)
    classified = n - cat_reviews[UNCLASSIFIED[0]]
    notes = []
    if n == 0:
        notes.append(note("NOT_COMPUTABLE"))
    elif n < SMALL_SAMPLE_REVIEWS:
        notes.append(note("SMALL_SAMPLE"))
    if n and unique / n < LOW_VARIETY_RATIO:
        notes.append({"code": "LOW_CONFIDENCE",
                      "message": f"서로 다른 리뷰 문장이 {unique}종뿐이라 같은 문장이 반복됩니다. 키워드 다양성이 낮습니다"})

    return {
        "basis": "review",
        "analyzed_count": n,
        "unique_text_count": unique,
        "classified_count": classified,
        "unclassified_count": cat_reviews[UNCLASSIFIED[0]],
        "multi_label_count": multi,
        "categories": categories,
        "top_keywords": top_keywords,
        "sample_review": None if best is None else {
            "order_id": best[1]["order_id"], "product_id": best[1]["product_id"], "text": best[1]["text"],
            "matches": [{"keyword": w, "category": c, "category_label": LABEL[c]} for c, hs in best[2].items() for w in hs],
        },
        "reason_code_cross": [{"reason_code": rc, "category": c, "count": v}
                              for (rc, c), v in sorted(cross.items(), key=lambda kv: -kv[1])],
        "inputs": {"analyzed_count": n, "classified_count": classified},
        "formula": "분류 비율 = 분류별 리뷰 수 ÷ 분석 리뷰 수 × 100 (한 리뷰가 여러 분류면 각각 1건, 합계 100% 초과 가능)",
        "notes": notes,
    }


def review_keywords(conn: sqlite3.Connection, date_from: str, date_to: str, product_id: str | None = None) -> dict:
    """기간(주문일 기준)·상품의 반품 리뷰를 읽어 분류합니다. 반품률 API 와 같은 기간 기준입니다."""
    where = "s.sold_at BETWEEN ? AND ? AND r.return_detail_text IS NOT NULL AND TRIM(r.return_detail_text) <> ''"
    params: list = [date_from, date_to]
    if product_id:
        where += " AND s.product_id = ?"
        params.append(product_id)
    rows = conn.execute(
        f"""SELECT r.order_id, s.product_id, r.return_detail_text AS text, r.return_type_code AS reason_code
            FROM returns r JOIN sales s ON s.order_id = r.order_id
            WHERE {where} ORDER BY r.rowid""",
        params,
    ).fetchall()
    total_returns = conn.execute(
        f"SELECT COUNT(*) FROM returns r JOIN sales s ON s.order_id = r.order_id WHERE s.sold_at BETWEEN ? AND ?"
        + (" AND s.product_id = ?" if product_id else ""), params).fetchone()[0]
    result = analyze_texts([dict(r) for r in rows])
    return {"period": {"from": date_from, "to": date_to}, "product_id": product_id,
            "return_count": total_returns, **result}
