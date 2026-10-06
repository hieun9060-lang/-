"""명령행 진입점.

  python -m aeo_monitor run                 # 측정 + 분석 + 리포트 (매일 08:00 KST 자동 실행)
  python -m aeo_monitor notify              # 오늘 리포트 요약을 Slack/메일/GitHub 이슈로 발송 (09:00 KST)
  python -m aeo_monitor report [--date D]   # 저장된 측정으로 리포트만 다시 생성
  python -m aeo_monitor import-excel FILE   # 엑셀에서 질문 목록·기준선 재생성
  python -m aeo_monitor run --engines mock  # API 키 없이 데모
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import config
from .analyze import analyze_run
from .collect import run_collection, today_kst
from .engines import build_engines
from .insight import ai_briefing, rule_based
from .report import write_reports
from .schedule import select_daily, window_days
from .sources import SourceClassifier
from .storage import Store

log = logging.getLogger("aeo_monitor")


def _db_path(demo: bool) -> Path:
    return config.DATA_DIR / ("demo.db" if demo else "aeo.db")


def _baseline() -> dict | None:
    p = config.CONFIG_DIR / "baseline.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _site_url() -> str:
    if os.environ.get("REPORT_SITE_URL"):
        return os.environ["REPORT_SITE_URL"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}"
    return ""


def build_report(store: Store, run_id: int, settings: dict) -> dict:
    brands = config.load_brands()
    questions = _all_questions(settings, brands)
    a = analyze_run(store, run_id, brands, _baseline(), settings.get("trend_days", 14),
                    window_days(settings, questions))
    rules = rule_based(a)
    ai, ai_by = ("", "")
    if settings.get("ai_insight", True) and not a["run"]["demo"]:
        ai, ai_by = ai_briefing(a, settings.get("models"), settings.get("insight_engine", "gemini"))
    out = write_reports(store, a, rules, ai, config.DOCS_DIR, _site_url(), ai_by)
    log.info("리포트: %s", out["html"])
    return out


def _all_questions(settings: dict, brands) -> list:
    questions = config.load_questions(brands)
    if not settings.get("include_templates", True):
        questions = [q for q in questions if q.origin != "template"]
    return questions


def cmd_run(args) -> int:
    settings = config.load_settings()
    names = args.engines.split(",") if args.engines else settings.get("engines") or None
    if args.daily is not None:
        settings["daily_questions"] = args.daily
    engines = build_engines(names, settings.get("models"))
    if not engines:
        log.error("실행할 엔진이 없습니다. GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY 중 "
                  "하나 이상을 설정하거나 --engines mock 으로 데모를 실행하세요.")
        return 2
    log.info("엔진: %s", ", ".join(f"{e.name}({e.model})" for e in engines))
    brands = config.load_brands()
    if args.no_templates:
        settings["include_templates"] = False
    questions = _all_questions(settings, brands)
    run_date = args.date or today_kst()
    questions = select_daily(questions, settings, run_date)
    if args.limit:
        questions = questions[: args.limit]
    log.info("오늘 질문 %d개 (고정 %d · 순환 %d)", len(questions),
             sum(q.panel for q in questions), sum(not q.panel for q in questions))
    demo = any(e.name == "mock" for e in engines)
    store = Store(_db_path(demo))
    classifier = SourceClassifier(config.load_source_rules(), brands)
    run_id = run_collection(store, engines, questions, brands, classifier,
                            samples=args.samples or settings.get("samples_per_question", 1),
                            concurrency=settings.get("concurrency", 2), run_date=run_date)
    out = build_report(store, run_id, settings)
    print(out["html"])
    return 0


def cmd_report(args) -> int:
    store = Store(_db_path(args.demo))
    run = store.latest_run(args.date)
    if not run:
        log.error("저장된 측정이 없습니다.")
        return 1
    print(build_report(store, run["id"], config.load_settings())["html"])
    return 0


def cmd_notify(args) -> int:
    from .notify import send_all
    date = args.date or today_kst()
    md_path = config.DOCS_DIR / "reports" / f"{date}.md"
    if not md_path.exists():
        msg = f"⚠️ {date} AI 언급 리포트가 아직 생성되지 않았습니다. GitHub Actions 'Daily AI mention check' 로그를 확인하세요."
        send_all(f"[AI 언급 리포트] {date} 생성 실패", msg)
        log.error(msg)
        return 1
    target = config.load_brands().target.name
    sent = send_all(f"[AI 언급 리포트] {target} {date}", md_path.read_text(encoding="utf-8"))
    log.info("발송 채널: %s", ", ".join(sent) or "(설정된 채널 없음)")
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    from .server.app import create_app
    # X-Forwarded-* 는 TRUST_PROXY=1 일 때만 앱이 직접 해석한다(로그인 잠금 IP 위조 방지)
    uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=False, log_level="info")
    return 0


def _checkpoint(store: Store) -> None:
    """저장 전에 WAL 을 본 파일로 합쳐 DB 파일 하나만 보관해도 되게 한다."""
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    store.conn.execute("PRAGMA journal_mode=DELETE")


def cmd_build_site(args) -> int:
    """매일 실행(GitHub Actions): 설정 반영 → 수집·측정 → 정적 사이트 생성."""
    from .configsync import ConfigError, sync_config
    from .pipeline import run_pipeline
    from .repo import Repo
    from .staticsite import build_site, ensure_reports
    from .timeutil import today_kst
    db_path = config.DATA_DIR / "aeo.db"
    store = Store(db_path)
    repo = Repo(store)
    try:
        if not args.no_sync:
            try:
                res = sync_config(repo)
            except ConfigError as e:
                log.error("설정 파일 오류: %s", e)
                return 2
            log.info("설정 반영: 회사 %d · 채널 %d · 경고 %d", res["companies"], res["channels"], len(res["warnings"]))
            for w in res["warnings"]:
                log.warning("설정 경고: %s", w)
            if not res["channels"]:
                log.warning("수집할 채널 주소가 없습니다. config/monitor.yaml 의 channels 에 주소를 넣으세요.")
        if not args.skip_collect:
            jid = repo.create_job(args.kind, args.trigger)
            run_pipeline(db_path, args.kind, args.trigger, jid)
            j = repo.job(jid)
            log.info("수집 결과: %s — %s", j["status"], j["progress"])
        ensure_reports(repo, today_kst())
        info = build_site(repo, Path(args.out), args.repo, args.branch)
        log.info("사이트 생성: %s", info)
    finally:
        _checkpoint(store)
        store.close()
    return 0


def cmd_notify_db(args) -> int:
    from .notify import send_all
    from .pipeline import notification_markdown
    from .repo import Repo
    store = Store(config.DATA_DIR / "aeo.db")
    try:
        title, md = notification_markdown(Repo(store))
    finally:
        store.close()
    site = os.environ.get("SITE_URL", "").rstrip("/")
    if site:
        md += f"\n📱 대시보드: {site}/\n"
    sent = send_all(title, md)
    log.info("발송 채널: %s", ", ".join(sent) or "(설정된 채널 없음)")
    return 0


def cmd_demo_seed(args) -> int:
    from .demo import seed_demo
    if "AEO_DATA_DIR" not in os.environ and not args.force:
        log.error("운영 DB를 보호하기 위해 AEO_DATA_DIR 를 따로 지정하거나 --force 를 붙여야 합니다.")
        return 2
    seed_demo(Store(config.DATA_DIR / "aeo.db"))
    print("데모 데이터를 만들었습니다:", config.DATA_DIR / "aeo.db")
    return 0


def cmd_import(args) -> int:
    from .excel_import import import_excel
    print(import_excel(Path(args.file), config.CONFIG_DIR))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="aeo_monitor", description="AI 챗봇 학원 언급 모니터")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="측정 + 리포트")
    r.add_argument("--engines", help="쉼표 구분: claude,chatgpt,gemini,perplexity,mock")
    r.add_argument("--samples", type=int, help="질문당 반복 횟수")
    r.add_argument("--limit", type=int, help="질문 수 제한(시험용)")
    r.add_argument("--daily", type=int, help="하루 질문 수 (settings.yaml 의 daily_questions 덮어쓰기, 0 = 전체)")
    r.add_argument("--date", help="측정일 지정 YYYY-MM-DD (기본: 오늘 KST)")
    r.add_argument("--no-templates", action="store_true", help="학원별 동일 질문 제외")
    r.set_defaults(fn=cmd_run)
    rp = sub.add_parser("report", help="저장된 측정으로 리포트 재생성")
    rp.add_argument("--date")
    rp.add_argument("--demo", action="store_true")
    rp.set_defaults(fn=cmd_report)
    n = sub.add_parser("notify", help="오늘 리포트 알림 발송")
    n.add_argument("--date")
    n.set_defaults(fn=cmd_notify)
    sv = sub.add_parser("serve", help="웹 서비스 실행 (대시보드 + 일일 스케줄러)")
    sv.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    sv.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    sv.set_defaults(fn=cmd_serve)
    bs = sub.add_parser("build-site", help="설정 반영 + 수집·측정 + 정적 사이트 생성 (GitHub Actions 용)")
    bs.add_argument("--out", default="site")
    bs.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    bs.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", ""))
    bs.add_argument("--trigger", default="schedule")
    bs.add_argument("--kind", choices=["all", "content"], default="all", help="content = AI 언급 측정 없이 채널 수집만")
    bs.add_argument("--skip-collect", action="store_true", help="수집·측정 없이 사이트만 다시 생성")
    bs.add_argument("--no-sync", action="store_true", help="config 파일을 DB에 반영하지 않음 (데모용)")
    bs.set_defaults(fn=cmd_build_site)
    nd = sub.add_parser("notify-db", help="저장된 데이터로 요약 알림 발송 (GitHub 이슈·Slack·이메일)")
    nd.set_defaults(fn=cmd_notify_db)
    ds = sub.add_parser("demo-seed", help="화면 미리보기용 가짜 데이터 생성")
    ds.add_argument("--force", action="store_true")
    ds.set_defaults(fn=cmd_demo_seed)
    im = sub.add_parser("import-excel", help="엑셀에서 질문/기준선 가져오기")
    im.add_argument("file")
    im.set_defaults(fn=cmd_import)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
