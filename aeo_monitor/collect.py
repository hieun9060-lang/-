"""질문 × 엔진을 실행해 답변·언급·출처를 저장."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from .config import BrandConfig, Question
from .detect import detect_group_only, detect_mentions, text_mentions_brand
from .engines import Engine, EngineResult
from .sources import SourceClassifier
from .storage import Store

KST = timezone(timedelta(hours=9))
log = logging.getLogger(__name__)


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def process_result(res: EngineResult, brands: BrandConfig, classifier: SourceClassifier):
    mentions = detect_mentions(res.answer, brands)
    group_info = detect_group_only(res.answer, brands, mentions)
    cites = []
    for c in res.citations:
        url, domain = classifier.resolve(c.url, c.title)
        cites.append({
            "url": c.url,
            "domain": domain,
            "title": c.title,
            "source_type": classifier.classify(url, c.title),
            "cited_in_answer": c.cited_in_answer,
            "mentions_target": text_mentions_brand(f"{c.title} {c.cited_text}", brands.target)
            or classifier.classify(url) == "공식 홈페이지(이천캠퍼스)",
        })
    return mentions, group_info, cites


def run_collection(store: Store, engines: list[Engine], questions: list[Question], brands: BrandConfig,
                   classifier: SourceClassifier, samples: int = 1, concurrency: int = 4,
                   run_date: str | None = None) -> int:
    run_date = run_date or today_kst()
    demo = any(e.name == "mock" for e in engines)
    run_id = store.new_run(run_date, datetime.now(KST).isoformat(timespec="seconds"),
                           [f"{e.name}:{e.model}" for e in engines], demo)
    jobs = [(q, e, s) for q in questions for e in engines for s in range(1, samples + 1)]
    log.info("run %s: %d questions × %d engines × %d samples = %d calls",
             run_id, len(questions), len(engines), samples, len(jobs))

    def work(job):
        q, e, s = job
        try:
            return job, e.ask(q.text)
        except Exception as exc:  # 한 건 실패가 전체 실행을 멈추지 않도록
            return job, EngineResult(e.name, e.model, error=f"{type(exc).__name__}: {exc}")

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        for fut in as_completed(futures):
            (q, e, s), res = fut.result()
            mentions, group_info, cites = process_result(res, brands, classifier)
            store.add_response(run_id, q, res.engine, res.model, s, res.answer, res.error,
                               group_info, mentions, cites)
            done += 1
            if done % 20 == 0 or done == len(jobs):
                log.info("  %d/%d", done, len(jobs))
    return run_id
