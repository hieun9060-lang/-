"""일일 작업: 채널 수집 → 업체 동향 요약 → AI 챗봇 언급 측정 → (월요일/1일) 주간·월간 분석 → 알림."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from . import config
from .analyze import analyze_run
from .collect import run_collection
from .content import ai as content_ai
from .content.collectors import collect_all
from .engines import build_engines
from .export import build_payload
from .insight import ai_briefing, rule_based
from .repo import Repo
from .schedule import select_daily, window_days
from .sources import SourceClassifier
from .storage import Store
from .timeutil import now_kst, shift_period, today_kst

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


def run_aeo(repo: Repo, progress: Progress = lambda s: None, run_date: str | None = None,
            engines_override: list[str] | None = None, limit: int | None = None) -> dict:
    """AI 챗봇 언급 측정 + 분석 결과 저장."""
    import json
    st = repo.aeo_settings()
    names = engines_override or st.get("engines") or None
    engines = build_engines(names, st.get("models"))
    if not engines:
        return {"skipped": "AI 엔진 API 키가 없습니다 (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)."}
    brands = repo.brand_config()
    if not brands.target_id:
        return {"skipped": "우리 회사가 지정되지 않았습니다."}
    questions = repo.load_questions(brands, st.get("include_templates", False))
    run_date = run_date or today_kst()
    questions = select_daily(questions, st, run_date)
    if limit:
        questions = questions[:limit]
    progress(f"AI 질문 {len(questions)}개 × 엔진 {len(engines)}개 측정 중")
    classifier = SourceClassifier(config.load_source_rules(), brands)
    run_id = run_collection(repo.store, engines, questions, brands, classifier,
                            samples=st.get("samples_per_question", 1), concurrency=st.get("concurrency", 2), run_date=run_date)
    progress("AI 언급 분석 중")
    baseline_path = config.CONFIG_DIR / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    all_q = repo.load_questions(brands, st.get("include_templates", False))
    a = analyze_run(repo.store, run_id, brands, baseline, st.get("trend_days", 14), window_days(st, all_q))
    rules = rule_based(a)
    ai, ai_by = ("", "")
    if st.get("ai_insight", True) and not a["run"]["demo"]:
        ai, ai_by = ai_briefing(a, st.get("models"), st.get("insight_engine", "gemini"))
    payload = build_payload(a, rules, ai, ai_by, {})
    repo.save_aeo_day(run_date, bool(a["run"]["demo"]), payload)
    k = a["kpi"]
    return {"run_id": run_id, "date": run_date, "questions": len(questions), "engines": [e.name for e in engines],
            "today_rate": k.get("today_rate"), "errors": k.get("errors", 0)}


def summarize_result(result: dict, errors: list[str]) -> str:
    parts = []
    c = result.get("content")
    if c:
        parts.append(f"채널 {c['channels']}개 수집(새 게시물 {c['new_posts']}건" + (f", 문제 채널 {c['problem_channels']}개" if c["problem_channels"] else "") + ")")
    a = result.get("ai")
    if a:
        parts.append(f"AI 언급 건너뜀: {a['skipped']}" if a.get("skipped") else f"AI 언급 측정 {a.get('questions', 0)}개 질문")
    if result.get("reports"):
        parts.append(f"{'·'.join(result['reports'])} 분석 생성")
    if errors:
        parts.append("일부 실패: " + " / ".join(errors))
    return " · ".join(parts) or "완료"


def run_pipeline(db_path: Path, kind: str, trigger: str, job_id: int, run_date: str | None = None) -> None:
    """kind: all | content | ai | analysis. 새 DB 연결로 실행 (백그라운드 스레드용)."""
    store = Store(db_path)
    repo = Repo(store)

    def progress(msg: str) -> None:
        repo.update_job(job_id, progress=msg)

    result: dict = {}
    errors: list[str] = []
    today = run_date or today_kst()
    try:
        if kind in ("all", "content"):
            progress("채널 수집 중")
            try:
                result["content"] = collect_all(repo, progress)
                progress("업체 동향 요약 중")
                for d in (today, shift_period("day", today, -1)):
                    content_ai.day_digest(repo, d)
            except Exception as e:  # noqa: BLE001
                log.exception("콘텐츠 수집 실패")
                errors.append(f"콘텐츠 수집: {e}")
        if kind in ("all", "ai"):
            try:
                result["ai"] = run_aeo(repo, progress, today)
            except Exception as e:  # noqa: BLE001
                log.exception("AI 언급 측정 실패")
                errors.append(f"AI 언급 측정: {e}")
        if kind in ("all", "analysis"):
            try:
                sched = repo.kv_get("schedule", {})
                if kind == "analysis" or sched.get("auto_analysis", True):
                    progress("주간·월간 분석 확인 중")
                    result["reports"] = content_ai.auto_reports(repo, today)
            except Exception as e:  # noqa: BLE001
                log.exception("분석 생성 실패")
                errors.append(f"분석: {e}")
        result["errors"] = errors
        repo.update_job(job_id, status="error" if errors and len(errors) >= (2 if kind == "all" else 1) else "done",
                        progress=summarize_result(result, errors)[:400], result=result)
    except Exception as e:  # noqa: BLE001
        log.exception("작업 실패")
        repo.update_job(job_id, status="error", progress=f"실패: {e}"[:300], result=result)
    finally:
        store.close()


class JobManager:
    """한 번에 하나의 작업만 실행."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, kind: str, trigger: str = "manual", run_date: str | None = None, sync: bool = False) -> int | None:
        with self._lock:
            if self.running():
                return None
            store = Store(self.db_path)
            try:
                jid = Repo(store).create_job(kind, trigger)
            finally:
                store.close()
            if sync:
                run_pipeline(self.db_path, kind, trigger, jid, run_date)
            else:
                self._thread = threading.Thread(target=run_pipeline, args=(self.db_path, kind, trigger, jid, run_date), daemon=True)
                self._thread.start()
            return jid


def notification_markdown(repo: Repo) -> tuple[str, str]:
    """09:00 알림(Slack/메일)용 제목·본문."""
    today = today_kst()
    yday = shift_period("day", today, -1)
    ours = repo.our_company()
    lines = [f"## {ours['name'] if ours else '학원'} 모니터링 요약 — {today}", ""]
    posts = repo.posts(yday, today, limit=100)
    if posts:
        by: dict[str, list[dict]] = {}
        for p in posts:
            by.setdefault(p["company_name"], []).append(p)
        lines.append(f"### 어제·오늘 새 게시물 {len(posts)}건")
        for name, ps in sorted(by.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"- **{name}** {len(ps)}건 — " + " / ".join(f"[{p['topic']}] {p['title'][:40]}" for p in ps[:2]))
    else:
        lines.append("### 어제·오늘 새 게시물 없음")
    bad = [c for c in repo.channels(active_only=True) if c["status"] in ("login", "error")]
    if bad:
        lines += ["", f"⚠️ 수집에 문제가 있는 채널 {len(bad)}개 — 앱의 '수집 관리'에서 확인하세요."]
    days = repo.aeo_days()
    if days:
        p = repo.aeo_day(days[-1]["date"]) or {}
        lines += ["", f"### AI 챗봇 언급 ({days[-1]['date']})"]
        lines += [f"- {b.replace('**', '')}" for b in (p.get("briefing") or [])[:5]]
        acts = p.get("actions") or []
        if acts:
            lines += ["", "**우선 과제**"] + [f"{i}. {a['title']}" for i, a in enumerate(acts[:3], 1)]
    return f"[기숙학원 모니터링] {today}", "\n".join(lines) + "\n"
