"""KST 기준 날짜 도우미."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> str:
    return now_kst().strftime("%Y-%m-%d")


def to_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # 월요일 시작


def period_range(kind: str, anchor: str) -> tuple[str, str]:
    """day/week/month/year 기준일을 포함하는 [시작, 끝] (YYYY-MM-DD)."""
    d = to_date(anchor)
    if kind == "day":
        s = e = d
    elif kind == "week":
        s = week_start(d)
        e = s + timedelta(days=6)
    elif kind == "month":
        s = d.replace(day=1)
        e = (s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1)) - timedelta(days=1)
    elif kind == "year":
        s, e = d.replace(month=1, day=1), d.replace(month=12, day=31)
    else:
        raise ValueError(kind)
    return s.isoformat(), e.isoformat()


def shift_period(kind: str, anchor: str, step: int) -> str:
    d = to_date(anchor)
    if kind == "day":
        d += timedelta(days=step)
    elif kind == "week":
        d += timedelta(days=7 * step)
    elif kind == "month":
        m = d.month - 1 + step
        y, m = d.year + m // 12, m % 12 + 1
        d = d.replace(year=y, month=m, day=1)
    elif kind == "year":
        d = d.replace(year=d.year + step, month=1, day=1)
    return d.isoformat()


def days_between(start: str, end: str) -> list[str]:
    s, e = to_date(start), to_date(end)
    return [(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]
