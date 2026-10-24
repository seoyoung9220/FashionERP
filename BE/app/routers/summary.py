"""수익성·홈
GET /api/profit      쿼리: from · to (기본 최근 30일, 기준일 = 데이터 마지막 날짜)
GET /api/dashboard
GET /api/sales/daily          쿼리: from · to (기본 최근 7일)        — 홈 '매출 흐름'
GET /api/sales/momentum       쿼리: window_days (기본 7)             — 판매 급증 참고값(판정 안 함)
GET /api/profit/monthly       쿼리: from · to (기본 전체 데이터 기간) — 매출·추정 기여이익 추이
GET /api/profit/categories    쿼리: from · to (기본 최근 30일)       — 카테고리별 매출 비중
"""
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.errors import validation_failed
from app.services.dashboard import summary
from app.services.profit_query import profit
from app.services.trends import category_sales, daily_sales, monthly_profit, sales_momentum
from app.utils import data_as_of, data_start, is_date, period_ending

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


def _period(date_from, date_to, default_from, default_to):
    date_from, date_to = date_from or default_from, date_to or default_to
    for col, v in (("from", date_from), ("to", date_to)):
        if not is_date(v):
            raise validation_failed("날짜 형식이 올바르지 않습니다",
                                    [{"column": col, "value": v, "message": "YYYY-MM-DD 형식이어야 합니다"}])
    if date_from > date_to:
        raise validation_failed("기간이 올바르지 않습니다", [{"column": "from", "value": date_from, "message": "from 은 to 보다 앞이어야 합니다"}])
    return date_from, date_to


@router.get("/sales/daily")
def get_sales_daily(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
                    conn=Depends(get_db)):
    return daily_sales(conn, *_period(date_from, date_to, *period_ending(data_as_of(conn), 7)))


@router.get("/sales/momentum")
def get_sales_momentum(window_days: int = Query(7, ge=1, le=90), conn=Depends(get_db)):
    return sales_momentum(conn, data_as_of(conn), window_days)


@router.get("/profit/monthly")
def get_profit_monthly(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
                       conn=Depends(get_db)):
    return monthly_profit(conn, *_period(date_from, date_to, data_start(conn).isoformat(), data_as_of(conn).isoformat()))


@router.get("/profit/categories")
def get_profit_categories(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
                          conn=Depends(get_db)):
    return category_sales(conn, *_period(date_from, date_to, *period_ending(data_as_of(conn), PROFIT_PERIOD_DAYS)))
