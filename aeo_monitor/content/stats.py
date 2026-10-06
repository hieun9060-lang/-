"""기간별 게시물 통계."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from ..repo import Repo
from ..timeutil import days_between, to_date
from .classify import ALL_TOPICS


def _month_buckets(start: str, end: str) -> list[str]:
    s, e = to_date(start), to_date(end)
    out, d = [], s.replace(day=1)
    while d <= e:
        out.append(d.strftime("%Y-%m"))
        d = (d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1))
    return out


def period_stats(repo: Repo, start: str, end: str, platform: str | None = None, only_with_channels: bool = True) -> dict:
    companies = repo.companies()
    if only_with_channels:
        with_ch = {c["company_id"] for c in repo.channels(active_only=True)}
        companies = [c for c in companies if c["id"] in with_ch]
    ids = {c["id"] for c in companies}
    rows = [r for r in repo.post_counts(start, end) if r["company_id"] in ids and (not platform or r["platform"] == platform)]

    span = (to_date(end) - to_date(start)).days
    monthly = span > 62
    buckets = _month_buckets(start, end) if monthly else days_between(start, end)
    key = (lambda d: d[:7]) if monthly else (lambda d: d)

    per_c: dict[str, dict] = {c["id"]: {"total": 0, "platform": Counter(), "topic": Counter(),
                                        "series": Counter()} for c in companies}
    all_platform, all_topic = Counter(), Counter()
    for r in rows:
        pc = per_c[r["company_id"]]
        pc["total"] += r["n"]
        pc["platform"][r["platform"]] += r["n"]
        pc["topic"][r["topic"]] += r["n"]
        pc["series"][key(r["date"])] += r["n"]
        all_platform[r["platform"]] += r["n"]
        all_topic[r["topic"]] += r["n"]

    return {
        "start": start, "end": end, "platform": platform or "all", "monthly": monthly, "buckets": buckets,
        "total": sum(all_platform.values()), "byPlatform": dict(all_platform),
        "byTopic": [{"topic": t, "n": all_topic.get(t, 0)} for t in ALL_TOPICS if all_topic.get(t, 0)],
        "companies": [{
            "id": c["id"], "name": c["name"], "role": c["role"], "color": c["color_idx"],
            "total": per_c[c["id"]]["total"], "byPlatform": dict(per_c[c["id"]]["platform"]),
            "byTopic": dict(per_c[c["id"]]["topic"]),
            "series": [per_c[c["id"]]["series"].get(b, 0) for b in buckets],
        } for c in companies],
    }


def previous_period(start: str, end: str) -> tuple[str, str]:
    s, e = to_date(start), to_date(end)
    n = (e - s).days + 1
    return (s - timedelta(days=n)).isoformat(), (s - timedelta(days=1)).isoformat()


def daily_counts(repo: Repo, start: str, end: str) -> dict[str, dict[str, int]]:
    """{날짜: {회사id: 건수}} (캘린더 주간/월간 보기용)."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for r in repo.post_counts(start, end):
        out[r["date"]][r["company_id"]] = out[r["date"]].get(r["company_id"], 0) + r["n"]
    return out
