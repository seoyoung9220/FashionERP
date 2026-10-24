"""가짜(직접 만든) 작은 CSV로 적재·검증·반품률·조치 저장을 확인합니다.
실제 데이터 없이도 백엔드가 맞게 동작하는지 미리 볼 수 있습니다.
"""
import pytest

from app.database import connect, init_db
from app.errors import AppError
from app.importers.loader import import_files
from app.services import tasks
from app.services.ai import analyze_returns
from app.services.returns import return_rates

BOM = "﻿"   # 엑셀이 붙이는 BOM

ORDERS = BOM + """date,product_id,product_name,category,order_id,size,color,is_returned,return_type_code,return_detail_text
2026-10-01,P002,와이드 데님 팬츠,하의/바지,P002-20261001-0001,M,Black,1,불량 제품,'지퍼 윗부분이 뻑뻑해서 반품합니다'
2026-10-02,P002,와이드 데님 팬츠,하의/바지,P002-20261002-0001,L,Navy,0,NA,NA
2026-10-03,P002,와이드 데님 팬츠,하의/바지,P002-20261003-0001,XL,Navy,1,바느질/마감,'실밥이 풀려 있어요'
2026-10-03,P002,와이드 데님 팬츠,하의/바지,P002-20261003-0001,XL,Navy,0,NA,NA
2026-10-04,P001,오버핏 울 코트,아우터,P001-20261004-0001,M,Brown,0,NA,NA
2026-10-05,P001,오버핏 울 코트,아우터,P001-20261005-0001,M,Brown,1,NA,NA
"""

PRODUCTS = BOM + """product_id,product_name,category,price,cost,lead_time_days,moq
P001,오버핏 울 코트,아우터,129000,52000,14,30
P002,와이드 데님 팬츠,하의/바지,48000,18000,10,50
"""
SUPPLIERS = "supplier_id,supplier_name\nS01,성수봉제\nS02,창신어패럴\n"
POS = """po_id,product_id,supplier_id,ordered_at,received_at,ordered_qty,received_qty,inspected_qty,defect_qty
PO2026-0312-01,P002,S01,2026-03-01,2026-03-12,200,200,200,16
PO2026-0401-01,P002,S09,2026-04-01,,100,,,
PO2026-0402-01,P001,S02,2026-04-02,2026-04-10,100,90,95,-2
"""
DEFECTS = "po_id,defect_type,defect_qty\nPO2026-0312-01,SEWING,11\nPO2026-0312-01,FABRIC,3\n"


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    yield c
    c.close()


def up(**kw):
    return {name: (f"{name}.csv", text.encode("utf-8")) for name, text in kw.items()}


def test_orders_split_into_sales_and_returns(conn):
    res = import_files(conn, up(sales=ORDERS))
    assert res["imported"] == {"sales": 5, "returns": 3}
    # 중복 order_id 행은 오류 (규칙 10)
    assert [e["row"] for e in res["errors"]] == [5]
    # products 가 없어서 규칙 12 생략 경고 + 반품인데 사유 NA 경고 (규칙 11)
    msgs = " ".join(w["message"] for w in res["warnings"])
    assert "규칙 12" in msgs and "반품 유형이 NA" in msgs

    r = conn.execute("SELECT * FROM returns ORDER BY return_id").fetchall()
    assert r[0]["return_id"] == "R0001"
    assert r[0]["return_type_code"] == "DEFECTIVE"           # 한글 라벨 → 영문 코드
    assert r[0]["return_detail_text"] == "지퍼 윗부분이 뻑뻑해서 반품합니다"   # 홑따옴표 제거
    assert r[1]["return_type_code"] == "QUALITY_FINISH"
    assert r[2]["return_type_code"] is None                  # "NA" → null


def test_missing_column_rejects_whole_upload(conn):
    bad = "product_id,product_name\nP001,코트\n"
    with pytest.raises(AppError) as e:
        import_files(conn, up(products=bad, suppliers=SUPPLIERS))
    assert e.value.status == 400 and e.value.code == "VALIDATION_FAILED"
    assert {d["column"] for d in e.value.details} == {"price", "cost", "lead_time_days", "moq"}
    # 파일 전체 거부: suppliers 도 저장되지 않아야 함
    assert conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0


def test_row_errors_and_warnings(conn):
    res = import_files(conn, up(products=PRODUCTS, suppliers=SUPPLIERS, purchase_orders=POS, defects=DEFECTS))
    assert res["imported"] == {"products": 2, "suppliers": 2, "purchase_orders": 1, "defects": 2}
    cols = {(e["row"], e["column"]) for e in res["errors"]}
    assert (3, "supplier_id") in cols          # 없는 거래처 (규칙 7)
    assert (4, "defect_qty") in cols           # 음수 (규칙 3)
    defect_msg = [e for e in res["errors"] if e["column"] == "defect_qty"][0]["message"]
    assert defect_msg == "수량은 0 이상의 정수여야 합니다"
    # 11 + 3 = 14 ≠ 16 → 경고만 (규칙 9)
    assert any("PO2026-0312-01의 불량 유형 합계" in w["message"] for w in res["warnings"])


def test_rule12_when_products_exist(conn):
    import_files(conn, up(products="product_id,product_name,category,price,cost,lead_time_days,moq\n"
                                   "P002,와이드 데님 팬츠,하의/바지,48000,18000,10,50\n"))
    res = import_files(conn, up(sales=ORDERS))
    assert any(e["column"] == "product_id" for e in res["errors"])   # P001 은 products 에 없음


def test_return_rates_from_db(conn):
    import_files(conn, up(sales=ORDERS))
    out = return_rates(conn, "2026-10-01", "2026-10-31")
    assert out["period"] == {"from": "2026-10-01", "to": "2026-10-31"}
    p002 = next(i for i in out["items"] if i["product_id"] == "P002")
    assert (p002["order_count"], p002["return_count"], p002["return_rate_pct"]) == (3, 2, 66.7)
    assert p002["basis"] == "count"
    assert {r["code"] for r in p002["reasons"]} == {"DEFECTIVE", "QUALITY_FINISH"}
    assert set(p002) >= {"inputs", "formula", "notes"}


def test_tasks_crud(conn):
    import_files(conn, up(sales=ORDERS))
    t = tasks.create_task(conn, {"product_id": "P002", "title": "허벅지 둘레 실측표 재확인",
                                 "type": "PRODUCT_FIX", "assignee": "시환", "due_date": "2026-10-28",
                                 "source": {"type": "RETURN_ANALYSIS", "ref": "P002"}})
    assert t["task_id"] == "T0001"
    assert t["status"] == "PENDING" and t["status_label"] == "대기"
    assert t["type_label"] == "실제 상품 수정"
    assert t["product_name"] == "와이드 데님 팬츠"

    t = tasks.update_task(conn, "T0001", {"status": "IN_PROGRESS"})
    assert t["status"] == "IN_PROGRESS"
    assert tasks.list_tasks(conn, status="IN_PROGRESS")["items"][0]["task_id"] == "T0001"

    with pytest.raises(AppError) as e:
        tasks.update_task(conn, "T9999", {"status": "DONE"})
    assert e.value.status == 404 and e.value.code == "NOT_FOUND"

    with pytest.raises(AppError) as e:
        tasks.update_task(conn, "T0001", {"due_date": "10/28"})
    assert e.value.status == 400


def test_ai_returns_fallback_200_without_key(conn):
    out = analyze_returns(conn, "P002", {"from": "2026-09-25", "to": "2026-10-24"})
    assert out["fallback"] is True
