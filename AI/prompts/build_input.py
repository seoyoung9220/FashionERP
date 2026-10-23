#!/usr/bin/env python3
"""
반품 분석 LLM 입력 페이로드 생성기.

AI/prompts/return-analysis.md 의 User 메시지 템플릿에 들어갈 JSON 을 만든다.
백엔드(태연)가 /api/returns/analyze 에서 같은 구조를 만들면 되는 참조 구현.

사용:
    python3 AI/prompts/build_input.py P002            # 압축형 (권장)
    python3 AI/prompts/build_input.py P002 --full     # 반품 1건 1행
    python3 AI/prompts/build_input.py P007 -o out.json

정본: datasets/product_return_dataset_2000.csv  (CONVENTIONS §2)
stock_tracked 를 쓰면 order_id 가 달라 근거 추적이 깨진다.
"""
import csv, json, collections, argparse, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ORDERS   = ROOT / "datasets/product_return_dataset_2000.csv"
PRODUCTS = ROOT / "DATA/sample/products.csv"
PO       = ROOT / "DATA/sample/purchase_orders.csv"
DEFECTS  = ROOT / "DATA/sample/defects.csv"
ENUMS    = ROOT / "DATA/enums.json"


def read(path):
    # 주문 CSV 에 UTF-8 BOM 이 있다. utf-8-sig 필수 (CONVENTIONS, DATA/dictionary.md)
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def pct(a, b):
    return round(a / b * 100 + 1e-9, 1) if b else None


def build(product_id, full=False):
    rows = read(ORDERS)
    for r in rows:
        # 자유 서술이 홑따옴표로 감싸져 있다
        r["return_detail_text"] = r["return_detail_text"].strip("'")

    enums = json.load(open(ENUMS, encoding="utf-8"))
    defect_label = {e["code"]: e["label"] for e in enums["defect_types"]}

    orders  = [r for r in rows if r["product_id"] == product_id]
    if not orders:
        sys.exit(f"상품 {product_id} 가 정본에 없습니다")
    returns = [r for r in orders if r["is_returned"] == "1"]

    # 고객이 선택한 사유 — 분류 입력이 아니라 대조용
    selected = [{"source_label": k, "count": v}
                for k, v in collections.Counter(r["return_type_code"] for r in returns).most_common()]

    # 분류 대상
    if full:
        items = [{"order_id": r["order_id"], "size": r["size"], "color": r["color"],
                  "text": r["return_detail_text"]} for r in returns]
    else:
        # 같은 문장이 반복되므로 묶어서 토큰을 아낀다.
        # order_ids 는 근거로 쓰이므로 생략하지 않는다 (AI/prompts/return-analysis.md)
        g = collections.OrderedDict()
        for r in returns:
            g.setdefault(r["return_detail_text"], []).append(r)
        items = [{"text": t, "count": len(v),
                  "order_ids": [x["order_id"] for x in v],
                  "sizes": sorted({x["size"] for x in v}),
                  "colors": sorted({x["color"] for x in v})}
                 for t, v in sorted(g.items(), key=lambda kv: -len(kv[1]))]

    dims = {}
    for d in ("size", "color"):
        c = collections.Counter(r[d] for r in returns)
        dims[d] = [{"value": k, "count": v, "share_pct": pct(v, len(returns))}
                   for k, v in c.most_common()]

    # 입고 검수 불량 — 해당 상품의 모든 발주 건 합산
    po_ids = {q["po_id"] for q in read(PO) if q["product_id"] == product_id}
    dc = collections.Counter()
    for d in read(DEFECTS):
        if d["po_id"] in po_ids:
            dc[d["defect_type"]] += int(d["defect_qty"])
    total_defect = sum(dc.values())
    defect_context = [{"code": k, "label": defect_label[k], "qty": v,
                       "share_pct": pct(v, total_defect)} for k, v in dc.most_common()]

    products = {r["product_id"]: r for r in read(PRODUCTS)}
    p = products.get(product_id, {})
    dates = sorted(r["date"] for r in orders)

    return {
        "product": {"product_id": product_id,
                    "product_name": orders[0]["product_name"],
                    "category": orders[0]["category"]},
        "period": {"from": dates[0], "to": dates[-1]},
        "stats": {"order_count": len(orders), "return_count": len(returns),
                  "return_rate_pct": pct(len(returns), len(orders))},
        "selected_reasons": selected,
        "returns": items,
        "dimension_counts": dims,
        "defect_context": defect_context,
        "defect_context_note": (
            f"{product_id} 의 발주 {len(po_ids)}건 입고 검수에서 확인된 불량 {total_defect}장. "
            "반품 건과 같은 물량인지는 확인되지 않았으므로 단정하지 말 것."
        ) if total_defect else None,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("product_id")
    ap.add_argument("--full", action="store_true", help="반품 1건을 1행으로 (압축 안 함)")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    out = json.dumps(build(a.product_id, a.full), ensure_ascii=False, indent=2)
    if a.out:
        pathlib.Path(a.out).write_text(out, encoding="utf-8")
        print(f"{a.out} 생성")
    else:
        print(out)
