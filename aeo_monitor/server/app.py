"""FastAPI 앱: API + 정적 화면 + 일일 스케줄러."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from ..pipeline import JobManager
from ..repo import Repo
from ..seed import seed_defaults
from ..storage import Store
from . import api
from .auth import Auth
from .scheduler import DailyScheduler

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")


def create_app(db_path: Path | None = None, start_scheduler: bool | None = None) -> FastAPI:
    db_path = db_path or (config.DATA_DIR / "aeo.db")
    if start_scheduler is None:
        start_scheduler = os.environ.get("DISABLE_SCHEDULER") != "1"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(db_path)
        try:
            repo = Repo(store)
            seed_defaults(repo)
            repo.fail_stale_jobs()
        finally:
            store.close()
        if start_scheduler:
            app.state.scheduler.start()
        yield
        app.state.scheduler.stop()

    app = FastAPI(title="기숙학원 모니터링", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.db_path = db_path
    app.state.auth = Auth()
    app.state.jobs = JobManager(db_path)
    app.state.scheduler = DailyScheduler(db_path, app.state.jobs)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("처리되지 않은 오류: %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "서버 오류가 발생했습니다."}, status_code=500)

    app.include_router(api.router)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def sw():
        return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    return app
