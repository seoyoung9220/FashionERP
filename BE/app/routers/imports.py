"""POST /api/imports — CSV 업로드 (multipart/form-data, 필드 이름 = 테이블 이름, 여러 파일 동시 가능)

주문 CSV(product_return_dataset_2000.csv)는 필드 이름 "sales" 로 올립니다.
POST /api/sales   — 화면에서 새 주문 1건 추가 (JSON, 표를 교체하지 않음) [계약변경]
"""
from fastapi import APIRouter, Depends, Request

from app.database import get_db
from app.errors import validation_failed
from app.importers.loader import import_files
from app.services.order_input import add_order

router = APIRouter(prefix="/api", tags=["업로드"])


@router.post("/imports")
async def upload(request: Request, conn=Depends(get_db)):
    form = await request.form()
    files = {}
    for field, value in form.multi_items():
        if hasattr(value, "read"):                # 파일만 받습니다
            files[field] = (value.filename or f"{field}.csv", await value.read())
    if not files:
        raise validation_failed("업로드된 파일이 없습니다")
    return import_files(conn, files)


@router.post("/sales", status_code=201)
def add_sale(body: dict, conn=Depends(get_db)):
    return add_order(conn, body)
