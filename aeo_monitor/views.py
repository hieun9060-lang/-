"""화면이 읽는 데이터 구성 (서버 API 와 정적 사이트 내보내기가 같은 함수를 쓴다)."""
from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter

from . import llm
from .analyze import analyze_run
from .content import ai as content_ai
from .content.classify import ALL_TOPICS
from .content.stats import daily_counts, period_stats, previous_period
from .repo import Repo
from .schedule import window_days
from .timeutil import period_range, shift_period, today_kst

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BadRequest(ValueError):
    pass


def safe_link(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else ""


def check_date(s: str | None) -> str:
    s = s or today_kst()
    if not DATE.match(s):
        raise BadRequest("날짜 형식은 YYYY-MM-DD 입니다.")
    return s


def post_json(p: dict) -> dict:
    return {"id": p["id"], "company_id": p["company_id"], "company": p.get("company_name", ""), "platform": p["platform"],
            "title": p["title"], "snippet": p["snippet"], "url": safe_link(p["url"]), "topic": p["topic"],
            "date": p["post_date"], "published_at": p["published_at"]}


def tracked(repo: Repo) -> list[dict]:
    """채널이 하나라도 있는 회사 (캘린더·통계에 표시)."""
    with_ch = {c["company_id"] for c in repo.channels(active_only=True)}
    return [c for c in repo.companies() if c["id"] in with_ch]


def company_json(repo: Repo, c: dict) -> dict:
    chans = repo.channels(c["id"])
    return {"id": c["id"], "name": c["name"], "role": c["role"], "color": c["color_idx"], "aliases": c["aliases"],
            "domains": c["domains"], "trackAi": c["track_ai"], "channels": chans,
            "posts": repo.post_total("2000-01-01", "2100-01-01", company_id=c["id"])}


def key_status() -> dict:
    return {"gemini": bool(os.environ.get("GEMINI_API_KEY")), "chatgpt": bool(os.environ.get("OPENAI_API_KEY")),
            "claude": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
            "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
            "slack": bool(os.environ.get("SLACK_WEBHOOK_URL")),
            "email": bool(os.environ.get("SMTP_HOST") and os.environ.get("REPORT_EMAIL_TO"))}


def build_bootstrap(repo: Repo, running: bool = False) -> dict:
    return {"today": today_kst(), "workspace": repo.kv_get("workspace", {}), "goal": repo.kv_get("goal", {}),
            "schedule": repo.kv_get("schedule", {}), "topics": ALL_TOPICS,
            "companies": [company_json(repo, c) for c in repo.companies()],
            "job": repo.latest_job(), "running": running, "keys": key_status()}


def build_calendar(repo: Repo, view: str, anchor: str | None) -> dict:
    anchor = check_date(anchor)
    start, end = period_range(view, anchor)
    comps = tracked(repo)
    posts = repo.posts(start, end, limit=3000)
    by_c: dict[str, list[dict]] = {}
    for p in posts:
        by_c.setdefault(p["company_id"], []).append(p)
    sums = repo.day_summaries(anchor) if view == "day" else {}
    cards = []
    for c in comps:
        ps = by_c.get(c["id"], [])
        s = sums.get(c["id"])
        rule = content_ai.rule_digest(c, ps) if ps else {"issue": "", "summary": "", "highlight": ""}
        topics = Counter(p["topic"] for p in ps)
        if s and ps:
            issue, summary, highlight, model = s["issue"], s["summary"], s["highlight"], s["model"]
        else:
            issue, summary, highlight, model = rule["issue"], rule["summary"], rule["highlight"], "규칙" if ps else ""
        cards.append({"id": c["id"], "name": c["name"], "role": c["role"], "color": c["color_idx"], "count": len(ps),
                      "issue": issue, "summary": summary, "highlight": highlight, "summaryBy": model,
                      "topics": dict(topics), "posts": [post_json(p) for p in ps[:60]]})
    return {"view": view, "anchor": anchor, "start": start, "end": end, "companies": cards,
            "total": sum(c["count"] for c in cards),
            "daily": daily_counts(repo, start, end) if view != "day" else {}, "hasChannels": bool(comps)}


def build_stats(repo: Repo, rng: str, anchor: str | None, platform: str = "all") -> dict:
    anchor = check_date(anchor)
    start, end = period_range(rng, anchor)
    allp = period_stats(repo, start, end)
    ps, pe = previous_period(start, end)
    graph = allp if platform == "all" else period_stats(repo, start, end, platform)
    return {"range": rng, "anchor": anchor, "start": start, "end": end, "total": allp["total"],
            "prevTotal": period_stats(repo, ps, pe)["total"], "byPlatform": allp["byPlatform"],
            "graph": graph, "topics": graph["byTopic"], "platform": platform}


def evidence_filters(company: str | None, topic: str | None, days: str, q: str | None) -> dict:
    end = today_kst()
    start = "2000-01-01" if days == "all" else shift_period("day", end, -(int(days) - 1)) if days.isdigit() else "2000-01-01"
    return {"start": start, "end": "2100-01-01", "company_id": company or None, "topic": topic or None,
            "q": (q or "").strip()[:80] or None}


def build_evidence(repo: Repo, company, topic, days, q, offset: int = 0, limit: int = 50) -> dict:
    f = evidence_filters(company, topic, days, q)
    limit = max(1, min(limit, 200))
    start, end = f.pop("start"), f.pop("end")
    items = repo.posts(start, end, limit=limit, offset=max(0, offset), **f)
    return {"total": repo.post_total(start, end, **f), "items": [post_json(p) for p in items], "topics": repo.post_topics()}


def build_evidence_csv(repo: Repo, company, topic, days, q) -> str:
    f = evidence_filters(company, topic, days, q)
    start, end = f.pop("start"), f.pop("end")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["날짜", "회사", "채널", "주제", "제목", "요약", "원문 주소"])
    for p in repo.posts(start, end, limit=20000, **f):
        cells = [p["post_date"], p["company_name"], p["platform"], p["topic"], p["title"], p["snippet"], p["url"]]
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in "=+-@" else c for c in cells])  # 엑셀 수식 주입 방지
    return "﻿" + buf.getvalue()


def build_questions(repo: Repo) -> dict:
    return {"questions": repo.questions(), "daily": repo.kv_get("aeo", {}).get("daily_questions", 10)}


def build_analysis(repo: Repo, kind: str, anchor: str | None) -> dict:
    anchor = check_date(anchor)
    start, end = period_range(kind, anchor)
    r = repo.report(kind, start)
    return {"kind": kind, "anchor": anchor, "start": start, "end": end, "report": r["payload"] if r else None,
            "ai": bool(llm.available())}


def build_settings(repo: Repo) -> dict:
    from .engines import REGISTRY
    return {"goal": repo.kv_get("goal", {}), "schedule": repo.kv_get("schedule", {}), "aeo": repo.kv_get("aeo", {}),
            "keys": key_status(), "allEngines": [e for e in REGISTRY if e != "mock"]}


def build_aeo_index(repo: Repo, demo: bool = False) -> dict:
    days = repo.aeo_days(demo)
    return {"days": days, "latest": days[-1]["date"] if days else None}


def build_aeo_day(repo: Repo, date: str, demo: bool = False, xlsx_url: str | None = None) -> dict | None:
    p = repo.aeo_day(check_date(date), demo)
    if p is not None:
        p["files"] = {"xlsx": xlsx_url or (f"/api/aeo/{date}.xlsx" + ("?demo=1" if demo else ""))}
    return p


def build_aeo_xlsx(repo: Repo, date: str, demo: bool = False) -> bytes | None:
    from .report import write_xlsx
    date = check_date(date)
    run = repo.store.latest_run(date)
    if not run or bool(run["demo"]) != demo:
        return None
    brands = repo.brand_config()
    st = repo.aeo_settings()
    a = analyze_run(repo.store, run["id"], brands, None, st.get("trend_days", 14),
                    window_days(st, repo.load_questions(brands, st.get("include_templates", False))))
    buf = io.BytesIO()
    write_xlsx(repo.store, a, buf, brands)
    return buf.getvalue()
