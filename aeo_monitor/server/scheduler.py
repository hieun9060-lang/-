"""매일 정해진 시각에 실행: 수집·측정(run_time), 알림(notify_time). 서버가 꺼져 있었다면 켜질 때 따라잡는다."""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .. import notify
from ..pipeline import JobManager, notification_markdown
from ..repo import Repo
from ..storage import Store
from ..timeutil import KST, now_kst, today_kst

log = logging.getLogger(__name__)


class DailyScheduler:
    def __init__(self, db_path, jobs: JobManager):
        self.db_path = db_path
        self.jobs = jobs
        self.sched = BackgroundScheduler(timezone=KST)

    def _times(self) -> tuple[str, str]:
        store = Store(self.db_path)
        try:
            s = Repo(store).kv_get("schedule", {})
        finally:
            store.close()
        return s.get("run_time", "07:00"), s.get("notify_time", "09:00")

    def _run(self) -> None:
        if self.jobs.start("all", "schedule") is None:
            log.warning("이전 작업이 아직 실행 중이라 예약 실행을 건너뜁니다.")

    def _notify(self) -> None:
        store = Store(self.db_path)
        try:
            title, md = notification_markdown(Repo(store))
        finally:
            store.close()
        sent = notify.send_all(title, md)
        log.info("알림 발송: %s", ", ".join(sent) or "(설정된 채널 없음)")

    def reconfigure(self) -> None:
        run_t, notify_t = self._times()
        for job_id, fn, t in (("daily-run", self._run, run_t), ("daily-notify", self._notify, notify_t)):
            h, m = (int(x) for x in t.split(":"))
            self.sched.add_job(fn, "cron", hour=h, minute=m, id=job_id, replace_existing=True,
                               misfire_grace_time=3 * 3600, coalesce=True, max_instances=1)

    def start(self) -> None:
        self.reconfigure()
        self.sched.start()
        threading.Timer(20, self.catch_up).start()

    def stop(self) -> None:
        if self.sched.running:
            self.sched.shutdown(wait=False)

    def catch_up(self) -> None:
        """오늘 실행 시각이 지났는데 오늘 수집이 없으면 지금 실행 (서버 재시작/절전 대비)."""
        try:
            run_t, _ = self._times()
            h, m = (int(x) for x in run_t.split(":"))
            now = now_kst()
            if now < now.replace(hour=h, minute=m, second=0, microsecond=0):
                return
            store = Store(self.db_path)
            try:
                repo = Repo(store)
                done = [j for j in repo.recent_jobs(20) if j["started_at"][:10] == today_kst()
                        and j["kind"] in ("all", "content") and j["status"] in ("done", "running")]
            finally:
                store.close()
            if not done:
                log.info("오늘 예약 수집이 없어 지금 실행합니다 (catch-up).")
                self.jobs.start("all", "catchup")
        except Exception:  # noqa: BLE001
            log.exception("catch-up 실패")
