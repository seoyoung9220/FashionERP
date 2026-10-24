"""반품 분석
GET  /api/returns/rates     — 상품별 반품률·사유 비중
GET  /api/returns/review-keywords — 반품 리뷰 키워드 자동 분류 (규칙 기반)
POST /api/returns/analyze   — AI 반품 원인 분석 (실패 시 폴백 200)
"""
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.errors import validation_failed
from app.schemas import AnalyzeRequest
from app.services.ai import analyze_returns
from app.services.returns import return_rates
from app.services.review_keywords import review_keywords
from app.utils import data_as_of, data_start, is_date

router = APIRouter(prefix="/api/returns", tags=["반품"])


@router.get("/rates")
def get_return_rates(
    date_from: str | None = Query(None, alias="from", description="YYYY-MM-DD (기본: 전체 데이터 기간의 첫날)"),
    date_to: str | None = Query(None, alias="to", description="YYYY-MM-DD (기본: 데이터 마지막 날)"),
    product_id: str | None = None,
    conn=Depends(get_db),
):
    # 기본 = 전체 데이터 기간. metrics.md 기준값·expected-metrics.md·대시보드 worst_product·AI analyzed_count 가
    # 모두 전체 기간이라 화면마다 숫자가 달라지지 않게 맞춥니다. from·to 를 주면 그 기간으로 계산합니다.
    d_from, d_to = data_start(conn).isoformat(), data_as_of(conn).isoformat()
    date_from, date_to = date_from or d_from, date_to or d_to
    for col, v in (("from", date_from), ("to", date_to)):
        if not is_date(v):
            raise validation_failed("날짜 형식이 올바르지 않습니다",
                                    [{"column": col, "value": v, "message": "YYYY-MM-DD 형식이어야 합니다"}])
    return return_rates(conn, date_from, date_to, product_id)


@router.get("/review-keywords")
def get_review_keywords(
    date_from: str | None = Query(None, alias="from", description="YYYY-MM-DD (기본: 전체 데이터 기간의 첫날)"),
    date_to: str | None = Query(None, alias="to", description="YYYY-MM-DD (기본: 데이터 마지막 날)"),
    product_id: str | None = None,
    conn=Depends(get_db),
):
    # 기간 기본값·검증은 반품률(/rates)과 같습니다
    date_from, date_to = date_from or data_start(conn).isoformat(), date_to or data_as_of(conn).isoformat()
    for col, v in (("from", date_from), ("to", date_to)):
        if not is_date(v):
            raise validation_failed("날짜 형식이 올바르지 않습니다",
                                    [{"column": col, "value": v, "message": "YYYY-MM-DD 형식이어야 합니다"}])
    return review_keywords(conn, date_from, date_to, product_id)


@router.post("/analyze")
def post_analyze(body: AnalyzeRequest, conn=Depends(get_db)):
    return analyze_returns(conn, body.product_id, body.period.as_dict())
