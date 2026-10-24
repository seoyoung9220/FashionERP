"""리뷰 키워드 자동 분류 — 실제 주문 CSV(datasets/product_return_dataset_2000.csv)의 리뷰로 검증."""
import pytest

from app.database import connect, init_db
from app.importers.loader import seed_if_empty
from app.services.review_keywords import analyze_texts, classify, review_keywords


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    seed_if_empty(c)
    yield c
    c.close()


def test_real_sentences_are_classified_by_their_words():
    assert classify("사이즈가 작게 나와서 한 사이즈 큰 걸로 다시 사야겠어요") == {"SIZE_FIT": ["사이즈", "작게"]}
    assert classify("지퍼 윗부분이 뻑뻑해서 잘 잠기지 않습니다") == {"QUALITY": ["지퍼", "뻑뻑", "잠기지 않"]}
    assert classify("실내 조명에서 보면 사진과 색감 차이가 꽤 납니다") == {"COLOR": ["색감", "사진과"]}
    assert classify("실물을 보니 생각했던 느낌이 아니네요") == {"DESIGN": ["실물", "느낌이 아니"]}
    assert classify("원단이 너무 얇아서 찬 바람을 못 막아주네요") == {"FABRIC": ["원단", "얇아"]}
    assert classify("박스가 다 찌그러져서 상품 패키지가 손상되었습니다") == {"SHIPPING": ["박스", "찌그러", "패키지", "손상"]}
    # "다른 색상" 은 색상 '차이'가 아니라 고객의 선택 변경 → 색상 차이로 세지 않음
    assert classify("다른 색상이 더 나을 것 같아서 반품합니다") == {"CHANGE_OF_MIND": ["다른 색상", "더 나을 것 같"]}


def test_no_cause_or_empty_is_unclassified():
    assert classify("기타 사유로 인한 반품 요청입니다") == {"UNCLASSIFIED": []}
    assert classify("") == {"UNCLASSIFIED": []}
    assert classify(None) == {"UNCLASSIFIED": []}
    assert classify("감사합니다") == {"UNCLASSIFIED": []}


def test_multi_label_counts_each_category_once_and_share_can_exceed_100():
    rows = [{"order_id": "A", "product_id": "P1", "text": "사이즈도 작고 실밥도 튀어나왔어요", "reason_code": "SIZE_FIT"},
            {"order_id": "B", "product_id": "P1", "text": "기타 사유로 인한 반품 요청입니다", "reason_code": "OTHER"}]
    r = analyze_texts(rows)
    by = {c["code"]: (c["count"], c["share_pct"]) for c in r["categories"]}
    assert by == {"SIZE_FIT": (1, 50.0), "QUALITY": (1, 50.0), "UNCLASSIFIED": (1, 50.0)}   # 합계 150%
    assert (r["multi_label_count"], r["classified_count"], r["unclassified_count"]) == (1, 1, 1)


def test_real_data_totals(conn):
    r = review_keywords(conn, "2026-01-10", "2026-10-24")
    assert (r["return_count"], r["analyzed_count"], r["unique_text_count"]) == (184, 184, 17)
    by = {c["code"]: c["count"] for c in r["categories"]}
    assert by == {"QUALITY": 44, "CHANGE_OF_MIND": 40, "SIZE_FIT": 36, "COLOR": 24, "DESIGN": 22,
                  "FABRIC": 8, "SHIPPING": 5, "UNCLASSIFIED": 5}
    assert sum(by.values()) == 184 and r["multi_label_count"] == 0       # 이번 데이터는 다중 분류 없음
    assert r["categories"][0]["share_pct"] == 23.9                        # 44 ÷ 184
    assert r["notes"][0]["code"] == "LOW_CONFIDENCE"                      # 17종 문장 반복
    # 리뷰 문장은 원문 그대로 (적재 때 따옴표만 제거)
    assert not any(c["example"]["text"].startswith("'") for c in r["categories"])


def test_size_reviews_match_size_reason_code(conn):
    cross = {(x["reason_code"], x["category"]): x["count"] for x in review_keywords(conn, "2026-01-10", "2026-10-24")["reason_code_cross"]}
    assert cross[("SIZE_FIT", "SIZE_FIT")] == 36
    assert cross[("CHANGE_OF_MIND", "DESIGN")] == 22     # '단순 변심'을 고른 리뷰 중 실물·디자인 언급


def test_product_and_period_filters(conn):
    p = review_keywords(conn, "2026-01-10", "2026-10-24", "P002")
    assert p["analyzed_count"] == 57 and p["categories"][0] == {**p["categories"][0], "code": "SIZE_FIT", "count": 22, "share_pct": 38.6}
    assert review_keywords(conn, "2026-09-25", "2026-10-24")["analyzed_count"] == 26
    assert review_keywords(conn, "2030-01-01", "2030-01-31")["notes"][0]["code"] == "NOT_COMPUTABLE"


def test_sample_review_is_real_and_from_top_category(conn):
    r = review_keywords(conn, "2026-01-10", "2026-10-24")
    s = r["sample_review"]
    assert {m["category"] for m in s["matches"]} == {r["categories"][0]["code"]}      # 가장 많은 분류(품질·마감)
    real = {t for (t,) in conn.execute("SELECT return_detail_text FROM returns")}
    assert s["text"] in real                                                       # 만든 문장이 아니라 실제 리뷰
