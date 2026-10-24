"""재고·발주
GET /api/inventory           쿼리: sales_window_days (기본 7)
GET /api/inventory/reorder   쿼리: target_cover_days (기본 14) · sales_window_days (기본 7)
"""
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.services import stock
from app.utils import data_as_of

router = APIRouter(prefix="/api/inventory", tags=["재고·발주"])


@router.get("")
def get_inventory(sales_window_days: int = Query(7, ge=1), conn=Depends(get_db)):
    as_of = data_as_of(conn)
    return {
        "as_of": as_of.isoformat(),
        "sales_window_days": sales_window_days,
        "items": stock.inventory(conn, as_of, sales_window_days),
    }


@router.get("/reorder")
def get_reorder(target_cover_days: int = Query(14, ge=0), sales_window_days: int = Query(7, ge=1),
                conn=Depends(get_db)):
    as_of = data_as_of(conn)
    return {
        "as_of": as_of.isoformat(),
        "target_cover_days": target_cover_days,
        "items": stock.reorder(conn, as_of, target_cover_days, sales_window_days),
    }
