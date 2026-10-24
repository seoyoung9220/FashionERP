"""수익성·홈
GET /api/profit      쿼리: from · to (기본 최근 30일, 기준일 = 데이터 마지막 날짜)
GET /api/dashboard
"""
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.errors import validation_failed
from app.services.dashboard import summary
from app.services.profit_query import profit
from app.utils import data_as_of, is_date, period_ending

router = APIRouter(prefix="/api", tags=["수익성·홈"])
PROFIT_PERIOD_DAYS = 30   # metrics.md 기본값


@router.get("/profit")
def get_profit(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
               conn=Depends(get_db)):
    d_from, d_to = period_ending(data_as_of(conn), PROFIT_PERIOD_DAYS)
    date_from, date_to = date_from or d_from, date_to or d_to
    for col, v in (("from", date_from), ("to", date_to)):
        if not is_date(v):
            raise validation_failed("날짜 형식이 올바르지 않습니다",
                                    [{"column": col, "value": v, "message": "YYYY-MM-DD 형식이어야 합니다"}])
    return {"period": {"from": date_from, "to": date_to}, "items": profit(conn, date_from, date_to)}


@router.get("/dashboard")
def get_dashboard(conn=Depends(get_db)):
    as_of = data_as_of(conn)
    d_from, d_to = period_ending(as_of, PROFIT_PERIOD_DAYS)
    return summary(conn, as_of, d_from, d_to)
