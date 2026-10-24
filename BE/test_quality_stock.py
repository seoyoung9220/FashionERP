"""불량률·재고·발주량 조회: 발주 데이터가 없을 때 / 가짜 발주 데이터가 있을 때"""
from datetime import date

import pytest

from app.database import connect, init_db
from app.importers.loader import import_files
from app.services import stock
from app.services.quality import defect_rates

PRODUCTS = ("product_id,product_name,category,price,cost,lead_time_days,moq\n"
            "P002,와이드 데님 팬츠,하의/치마,48000,18000,10,50\n")
SUPPLIERS = "supplier_id,supplier_name\nS01,성수봉제\n"
# 이전 건 150검수/4불량 · 55검수/1불량 → 현재 200검수/16불량 (metrics.md 예시)
POS = ("po_id,product_id,supplier_id,ordered_at,received_at,ordered_qty,received_qty,inspected_qty,defect_qty\n"
       "PO2026-0101-01,P002,S01,2026-01-01,2026-01-10,150,150,150,4\n"
       "PO2026-0201-01,P002,S01,2026-02-01,2026-02-10,55,55,55,1\n"
       "PO2026-0312-01,P002,S01,2026-03-01,2026-03-12,200,200,200,16\n")
DEFECTS = ("po_id,defect_type,defect_qty\n"
           "PO2026-0312-01,SEWING,11\nPO2026-0312-01,FABRIC,3\nPO2026-0312-01,FINISH,2\n")
ORDERS = "date,product_id,product_name,category,order_id,size,color,is_returned,return_type_code,return_detail_text\n" + "".join(
    f"2026-10-{d:02d},P002,와이드 데님 팬츠,하의/치마,P002-202610{d:02d}-000{k},M,Blue,0,NA,NA\n"
    for d in range(18, 25) for k in range(1, 7))   # 7일 × 6건 = 42건 → 일평균 6.0
AS_OF = date(2026, 10, 24)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    yield c
    c.close()


def up(**kw):
    return {k: (f"{k}.csv", v.encode()) for k, v in kw.items()}


def test_no_purchase_orders(conn):
    import_files(conn, up(products=PRODUCTS, sales=ORDERS))
    assert defect_rates(conn, "po") == []                       # 빈 목록
    inv = stock.inventory(conn, AS_OF)[0]
    assert inv["stock_qty"] is None and inv["status"] == "UNKNOWN"
    assert inv["avg_daily_sales"] == 6.0                        # 판매량은 계산 가능
    assert inv["notes"][0]["code"] == "NOT_COMPUTABLE"
    ro = stock.reorder(conn, AS_OF)[0]
    assert ro["final_order_qty"] is None and ro["notes"][0]["code"] == "NOT_COMPUTABLE"


def test_with_purchase_orders(conn):
    res = import_files(conn, up(products=PRODUCTS, suppliers=SUPPLIERS, purchase_orders=POS,
                                defects=DEFECTS, sales=ORDERS))
    assert res["errors"] == []
    po = [i for i in defect_rates(conn, "po") if i["po_id"] == "PO2026-0312-01"][0]
    assert (po["defect_rate_pct"], po["prior_avg_pct"], po["spike_threshold_pct"], po["is_spike"]) == (8.0, 2.4, 3.7, True)
    assert (po["good_qty"], po["defect_loss_amount"]) == (184, 288000)
    assert [(t["code"], t["share_pct"]) for t in po["defect_types"]] == [("SEWING", 68.8), ("FABRIC", 18.8), ("FINISH", 12.5)]
    first = [i for i in defect_rates(conn, "po") if i["po_id"] == "PO2026-0101-01"][0]
    assert first["is_spike"] is False and first["notes"][0]["code"] == "SMALL_SAMPLE"

    sup = defect_rates(conn, "supplier")[0]
    assert (sup["supplier_id"], sup["po_count"], sup["defect_rate_pct"]) == ("S01", 3, 5.2)   # 21 ÷ 405

    inv = stock.inventory(conn, AS_OF)[0]
    assert inv["stock_qty"] == 405 - 21 - 42          # 양품 384 − 판매 42 + 반품 0 = 342
    assert inv["avg_daily_sales"] == 6.0 and inv["status"] == "OK"   # 342 ÷ 6.0 = 57.0일 ≤ 60

    ro = stock.reorder(conn, AS_OF)[0]
    assert ro["final_order_qty"] == 0                  # 재고 342 > 필요 144
