"""숫자·날짜 공통 규칙 (CONVENTIONS §4, §5, §7).

- 비율: 0~100, 소수 1자리   (0.08 이 아니라 8.0)
- 금액: 정수(원)
- 일수: 소수 1자리
- 날짜: "YYYY-MM-DD", KST 기준
- 반올림은 사사오입. (파이썬 기본 round()는 2.5 → 2 로 만들어서 쓰지 않습니다)
"""
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

KST = timezone(timedelta(hours=9))

# CONVENTIONS §7 화면 문구. 임의로 바꾸지 않습니다.
NOTE_MESSAGES = {
    "LOW_CONFIDENCE": "추정 신뢰도 낮음",
    "SMALL_SAMPLE": "표본 수 부족",
    "MISSING_COST": "일부 비용 미입력",
    "NOT_COMPUTABLE": "산출 불가",
    "AI_UNCERTAIN": "판단하기 어려움",
}


def note(code: str) -> dict:
    return {"code": code, "message": NOTE_MESSAGES[code]}


def round1(x: float | None) -> float | None:
    """비율·일수용: 소수 1자리 사사오입"""
    if x is None:
        return None
    return float(Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def to_won(x: float | None) -> int | None:
    """금액용: 정수 사사오입"""
    if x is None:
        return None
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pct(part: float, whole: float) -> float | None:
    """part / whole × 100 을 소수 1자리로. 분모가 0이면 None (0이 아님)."""
    if not whole:
        return None
    return round1(part / whole * 100)


def fmt_num(x) -> str:
    """formula 문자열용 숫자 표시: 1069200 → "1,069,200", 6.0 → "6.0" """
    if isinstance(x, int):
        return f"{x:,}"
    return f"{x:,.1f}"


def today_kst() -> date:
    return datetime.now(KST).date()


def default_period(days: int = 30) -> tuple[str, str]:
    """기본 기간: 오늘(KST) 포함 최근 N일. 예) 2026-09-25 ~ 2026-10-24"""
    to = today_kst()
    frm = to - timedelta(days=days - 1)
    return frm.isoformat(), to.isoformat()


def is_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return len(text) == 10
    except (TypeError, ValueError):
        return False


def data_as_of(conn) -> date:
    """기준 시점(as_of) = 주문 데이터의 마지막 날짜. 데이터가 없으면 오늘(KST).
    DATA/expected/expected-metrics.md 의 as_of(2026-10-24)도 데이터 마지막 날짜입니다.
    '오늘'로 하면 시연 날짜가 바뀔 때 최근 7일 판매가 0이 되어 모든 재고가 '판단 불가'가 됩니다."""
    row = conn.execute("SELECT MAX(sold_at) FROM sales").fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else today_kst()


def data_start(conn) -> date:
    """주문 데이터의 첫 날짜. 반품률 기본 기간(전체 데이터 기간)의 시작입니다. 데이터가 없으면 as_of."""
    row = conn.execute("SELECT MIN(sold_at) FROM sales").fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else data_as_of(conn)


def period_ending(as_of: date, days: int) -> tuple[str, str]:
    return (as_of - timedelta(days=days - 1)).isoformat(), as_of.isoformat()
