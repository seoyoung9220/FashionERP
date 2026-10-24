"""불량률
GET /api/quality/defect-rates   쿼리: group_by = po(기본) | product | supplier · product_id · supplier_id
"""
from fastapi import APIRouter, Depends

from app.database import get_db
from app.errors import validation_failed
from app.services.quality import GROUPS, defect_rates
from app.utils import data_as_of

router = APIRouter(prefix="/api/quality", tags=["불량률"])


@router.get("/defect-rates")
def get_defect_rates(group_by: str = "po", product_id: str | None = None, supplier_id: str | None = None,
                     conn=Depends(get_db)):
    if group_by not in GROUPS:
        raise validation_failed("group_by 값이 올바르지 않습니다",
                                [{"column": "group_by", "value": group_by, "message": "po, product, supplier 중 하나여야 합니다"}])
    return {
        "as_of": data_as_of(conn).isoformat(),
        "group_by": group_by,
        "items": defect_rates(conn, group_by, product_id, supplier_id),
    }
