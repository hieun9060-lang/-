"""정적 사이트 생성: 화면(web/)과 날짜별 JSON 데이터를 한 폴더로 만든다 (Cloudflare Pages 등에 올릴 수 있게).

서버 API 가 돌려주던 값을 미리 계산해 파일로 저장하므로, 서버 없이도 같은 화면이 동작한다.
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path

from . import views
from .content import ai as content_ai
from .content.stats import period_stats
from .repo import Repo
from .timeutil import KST, now_kst, period_range, shift_period, to_date, today_kst, week_start

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
PLATFORMS = ["all", "blog", "youtube", "homepage"]
XLSX_DAYS = 14

HEADERS = """/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  X-Robots-Tag: noindex, nofollow
  Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'
/data/*
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache
/
  Cache-Control: no-cache
"""


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")


def _period_starts(kind: str, first: str, last: str) -> list[str]:
    out, cur = [], period_range(kind, first)[0]
    while cur <= last:
        out.append(cur)
        cur = shift_period(kind, cur, 1)
    return out


def ensure_reports(repo: Repo, today: str, use_ai: bool = True) -> list[str]:
    """이번 주·이번 달 분석은 매일 갱신하고, 지난 주·지난 달 분석은 없으면 만든다."""
    made = []
    for kind in ("week", "month"):
        content_ai.generate_report(repo, kind, today, use_ai=use_ai)
        made.append(f"{kind}:current")
        prev = shift_period(kind, today, -1)
        if not repo.report(kind, period_range(kind, prev)[0]):
            content_ai.generate_report(repo, kind, prev, use_ai=use_ai)
            made.append(f"{kind}:previous")
    return made


def build_site(repo: Repo, out: Path, repo_slug: str = "", branch: str = "", days: int = 180, xlsx: bool = True) -> dict:
    today = today_kst()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_DIR, out, ignore=shutil.ignore_patterns("__pycache__"))
    meta = {"repo": repo_slug, "branch": branch, "generatedAt": now_kst().isoformat(timespec="minutes")}
    (out / "static/js/mode.js").write_text(
        "// 자동 생성: 정적 사이트 모드 (서버 없이 data/*.json 을 읽음)\nexport const STATIC = true;\n"
        f"export const META = {json.dumps(meta, ensure_ascii=False)};\n", encoding="utf-8")
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    # 404.html 이 있어야 Cloudflare Pages 가 없는 파일에 진짜 404 를 돌려준다 (없으면 index.html 을 대신 보냄)
    (out / "404.html").write_text('<!doctype html><meta charset="utf-8"><title>없음</title>페이지를 찾을 수 없습니다.', encoding="utf-8")
    data = out / "data"

    r = repo.conn.execute("SELECT MIN(post_date) FROM posts WHERE baseline=0").fetchone()[0]
    floor = (to_date(today) - timedelta(days=days - 1)).isoformat()
    first = max(r or today, floor)
    first = min(first, (to_date(today) - timedelta(days=13)).isoformat())  # 최소 2주는 이동 가능하게

    n_files = 0
    # 캘린더: 일간·주간·월간
    d = first
    while d <= today:
        _write(data / f"calendar/day/{d}.json", views.build_calendar(repo, "day", d)); n_files += 1
        d = shift_period("day", d, 1)
    for kind in ("week", "month"):
        for s in _period_starts(kind, first, today):
            _write(data / f"calendar/{kind}/{s}.json", views.build_calendar(repo, kind, s)); n_files += 1
    # 통계
    for kind in ("week", "month", "year"):
        for s in _period_starts(kind, first, today):
            for pf in PLATFORMS:
                _write(data / f"stats/{kind}/{pf}/{s}.json", views.build_stats(repo, kind, s, pf)); n_files += 1
    # 근거 자료
    posts = repo.posts("2000-01-01", "2100-01-01", limit=200_000)
    cutoff = (to_date(today) - timedelta(days=364)).isoformat()
    _write(data / "posts.json", {"items": [views.post_json(p) for p in posts if p["post_date"] >= cutoff],
                                 "topics": repo.post_topics()})
    # 분석 보고서
    for row in repo.conn.execute("SELECT kind, period_start FROM analysis_reports"):
        rep = repo.report(row["kind"], row["period_start"])
        _write(data / f"analysis/{row['kind']}/{row['period_start']}.json", rep["payload"]); n_files += 1
    # AI 언급
    idx = views.build_aeo_index(repo)
    _write(data / "aeo/index.json", idx)
    recent = {x["date"] for x in idx["days"][-XLSX_DAYS:]}
    for x in idx["days"]:
        xurl = None
        if xlsx and x["date"] in recent:
            blob = views.build_aeo_xlsx(repo, x["date"])
            if blob:
                (data / "aeo/xlsx").mkdir(parents=True, exist_ok=True)
                (data / f"aeo/xlsx/{x['date']}.xlsx").write_bytes(blob)
                xurl = f"data/aeo/xlsx/{x['date']}.xlsx"
        p = views.build_aeo_day(repo, x["date"], False, xlsx_url=xurl)
        p["files"] = {"xlsx": xurl}
        _write(data / f"aeo/day/{x['date']}.json", p); n_files += 1
    # 기타
    boot = views.build_bootstrap(repo) | {"static": True, "meta": meta, "configWarnings": repo.kv_get("config_warnings", [])}
    _write(data / "bootstrap.json", boot)
    _write(data / "questions.json", views.build_questions(repo))
    _write(data / "settings.json", views.build_settings(repo))
    _write(data / "chat-context.json", content_ai.chat_context(repo))
    _write(data / "meta.json", {**meta, "today": today, "job": repo.latest_job()})
    return {"out": str(out), "firstDate": first, "today": today, "files": n_files, "posts": len(posts), "aeoDays": len(idx["days"])}
