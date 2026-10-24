"""반품 분석
GET  /api/returns/rates     — 상품별 반품률·사유 비중
POST /api/returns/analyze   — AI 반품 원인 분석 (실패 시 폴백 200)
"""
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.errors import validation_failed
from app.schemas import AnalyzeRequest
from app.services.ai import analyze_returns
from app.services.returns import return_rates
from app.utils import data_as_of, is_date, period_ending

router = APIRouter(prefix="/api/returns", tags=["반품"])


@router.get("/rates")
def get_return_rates(
    date_from: str | None = Query(None, alias="from", description="YYYY-MM-DD (기본: 최근 30일)"),
    date_to: str | None = Query(None, alias="to", description="YYYY-MM-DD"),
    product_id: str | None = None,
    conn=Depends(get_db),
):
    d_from, d_to = period_ending(data_as_of(conn), 30)
    date_from, date_to = date_from or d_from, date_to or d_to
    for col, v in (("from", date_from), ("to", date_to)):
        if not is_date(v):
            raise validation_failed("날짜 형식이 올바르지 않습니다",
                                    [{"column": col, "value": v, "message": "YYYY-MM-DD 형식이어야 합니다"}])
    return return_rates(conn, date_from, date_to, product_id)


@router.post("/analyze")
def post_analyze(body: AnalyzeRequest, conn=Depends(get_db)):
    return analyze_returns(conn, body.product_id, body.period.as_dict())
