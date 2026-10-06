"""REST API."""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from typing import Iterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import config, llm, views
from ..analyze import analyze_run
from ..content import ai as content_ai
from ..content.classify import ALL_TOPICS
from ..content.collectors import collect_channel, detect_type
from ..content.fetch import FetchError, check_public_url
from ..content.stats import daily_counts, period_stats, previous_period
from ..engines import REGISTRY
from ..repo import Repo
from ..storage import Store
from ..timeutil import period_range, shift_period, today_kst
from .auth import COOKIE, MAX_AGE, require_auth

router = APIRouter(prefix="/api")
protected = APIRouter(dependencies=[Depends(require_auth)])

MAX_COMPANIES, MAX_CHANNELS = 40, 12
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_repo(request: Request) -> Iterator[Repo]:
    store = Store(request.app.state.db_path)
    try:
        yield Repo(store)
    finally:
        store.close()


def check_date(s: str | None) -> str:
    try:
        return views.check_date(s)
    except views.BadRequest as e:
        raise HTTPException(400, str(e))


safe_link, post_json, tracked, company_json, key_status = (
    views.safe_link, views.post_json, views.tracked, views.company_json, views.key_status)


# ---------------- 인증 ----------------
class LoginIn(BaseModel):
    password: str = Field(max_length=200)


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    auth = request.app.state.auth
    return {"authenticated": auth.valid(request.cookies.get(COOKIE)), "noAuth": auth.no_auth}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    auth = request.app.state.auth
    ip = auth.client_ip(request)
    wait = auth.locked(ip)
    if wait:
        raise HTTPException(429, f"로그인 시도가 너무 많습니다. {wait // 60 + 1}분 뒤 다시 시도하세요.")
    if request.headers.get("x-requested-with") != "aeo-app":
        raise HTTPException(403, "잘못된 요청입니다.")
    token = auth.check_password(ip, body.password)
    if not token:
        raise HTTPException(401, "비밀번호가 올바르지 않습니다.")
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax", secure=secure, path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# ---------------- 기본 정보 ----------------
@protected.get("/bootstrap")
def bootstrap(request: Request, repo: Repo = Depends(get_repo)):
    return views.build_bootstrap(repo, request.app.state.jobs.running())


# ---------------- 캘린더 ----------------
@protected.get("/calendar")
def calendar(view: Literal["day", "week", "month"] = "day", anchor: str | None = None, repo: Repo = Depends(get_repo)):
    check_date(anchor)
    return views.build_calendar(repo, view, anchor)


class DateIn(BaseModel):
    date: str


@protected.post("/summaries")
def make_summaries(body: DateIn, repo: Repo = Depends(get_repo)):
    date = check_date(body.date)
    res = content_ai.day_digest(repo, date, use_ai=True)
    return {"date": date, "companies": len(res), "models": sorted({v["model"] for v in res.values()})}


# ---------------- 통계 ----------------
@protected.get("/stats")
def stats(range: Literal["week", "month", "year"] = "month", anchor: str | None = None,
          platform: Literal["blog", "youtube", "homepage", "rss", "all"] = "all", repo: Repo = Depends(get_repo)):
    check_date(anchor)
    return views.build_stats(repo, range, anchor, platform)


# ---------------- 근거 자료 ----------------
@protected.get("/evidence")
def evidence(company: str | None = None, topic: str | None = None, days: str = "all", q: str | None = None,
             offset: int = 0, limit: int = 50, repo: Repo = Depends(get_repo)):
    return views.build_evidence(repo, company, topic, days, q, offset, limit)


@protected.get("/evidence.csv")
def evidence_csv(company: str | None = None, topic: str | None = None, days: str = "all", q: str | None = None,
                 repo: Repo = Depends(get_repo)):
    return Response(views.build_evidence_csv(repo, company, topic, days, q), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="evidence.csv"'})


# ---------------- 회사·채널 관리 ----------------
class ChannelIn(BaseModel):
    url: str = Field(max_length=500)
    type: Literal["auto", "blog", "youtube", "homepage", "rss"] = "auto"
    label: str = Field(default="", max_length=60)


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    role: Literal["ours", "competitor"] = "competitor"
    color: int | None = Field(default=None, ge=0, le=7)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    domains: list[str] = Field(default_factory=list, max_length=20)
    trackAi: bool = True
    channels: list[ChannelIn] = Field(default_factory=list, max_length=MAX_CHANNELS)


class CompanyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    role: Literal["ours", "competitor"] | None = None
    color: int | None = Field(default=None, ge=0, le=7)
    aliases: list[str] | None = Field(default=None, max_length=30)
    domains: list[str] | None = Field(default=None, max_length=20)
    trackAi: bool | None = None
    active: bool | None = None


def _clean_list(items: list[str], maxlen: int = 80) -> list[str]:
    return list(dict.fromkeys(x.strip()[:maxlen] for x in items if x and x.strip()))


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        raise HTTPException(400, "주소를 입력하세요.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    try:
        check_public_url(url)
    except FetchError as e:
        raise HTTPException(400, str(e))
    return url


def _add_channel(repo: Repo, cid: str, ch: ChannelIn, collect: bool = True) -> dict:
    if len(repo.channels(cid)) >= MAX_CHANNELS:
        raise HTTPException(400, f"회사당 채널은 최대 {MAX_CHANNELS}개입니다.")
    url = normalize_url(ch.url)
    typ = detect_type(url) if ch.type == "auto" else ch.type
    if any(c["url"] == url for c in repo.channels(cid)):
        raise HTTPException(409, "이미 등록된 주소입니다.")
    chid = repo.add_channel(cid, typ, url, ch.label.strip())
    if collect:
        collect_channel(repo, repo.channel(chid))
    return repo.channel(chid)


@protected.post("/companies")
def create_company(body: CompanyIn, repo: Repo = Depends(get_repo)):
    if len(repo.companies(active_only=False)) >= MAX_COMPANIES:
        raise HTTPException(400, f"회사는 최대 {MAX_COMPANIES}개입니다.")
    name = body.name.strip()
    if any(c["name"] == name for c in repo.companies(active_only=False)):
        raise HTTPException(409, "같은 이름의 회사가 이미 있습니다.")
    cid = repo.create_company({"name": name, "role": body.role, "template_name": name,
                               "aliases": _clean_list(body.aliases or [name], 60), "domains": _clean_list(body.domains, 80),
                               "track_ai": body.trackAi, **({"color_idx": body.color} if body.color is not None else {})})
    errors = []
    for ch in body.channels:
        try:
            _add_channel(repo, cid, ch)
        except HTTPException as e:
            errors.append(f"{ch.url}: {e.detail}")
    return {"company": company_json(repo, repo.company(cid)), "errors": errors}


@protected.patch("/companies/{cid}")
def update_company(cid: str, body: CompanyPatch, repo: Repo = Depends(get_repo)):
    c = repo.company(cid)
    if not c:
        raise HTTPException(404, "회사를 찾을 수 없습니다.")
    if body.role == "competitor" and c["role"] == "ours" and body.active is not False:
        raise HTTPException(400, "우리 회사를 바꾸려면 다른 회사를 '우리 회사'로 지정하세요.")
    d: dict = {}
    if body.name is not None:
        d["name"] = body.name.strip()
    if body.role is not None:
        d["role"] = body.role
    if body.color is not None:
        d["color_idx"] = body.color
    if body.aliases is not None:
        d["aliases"] = _clean_list(body.aliases, 60)
    if body.domains is not None:
        d["domains"] = _clean_list(body.domains, 80)
    if body.trackAi is not None:
        d["track_ai"] = body.trackAi
    if body.active is not None:
        d["active"] = body.active
    repo.update_company(cid, d)
    return company_json(repo, repo.company(cid))


@protected.delete("/companies/{cid}")
def delete_company(cid: str, repo: Repo = Depends(get_repo)):
    c = repo.company(cid)
    if not c:
        raise HTTPException(404, "회사를 찾을 수 없습니다.")
    if c["role"] == "ours":
        raise HTTPException(400, "우리 회사는 삭제할 수 없습니다. 다른 회사를 '우리 회사'로 지정한 뒤 삭제하세요.")
    repo.delete_company(cid)
    return {"ok": True}


@protected.post("/companies/{cid}/channels")
def add_channel(cid: str, body: ChannelIn, repo: Repo = Depends(get_repo)):
    if not repo.company(cid):
        raise HTTPException(404, "회사를 찾을 수 없습니다.")
    return _add_channel(repo, cid, body)


class ChannelPatch(BaseModel):
    url: str | None = Field(default=None, max_length=500)
    type: Literal["blog", "youtube", "homepage", "rss"] | None = None
    label: str | None = Field(default=None, max_length=60)
    active: bool | None = None


@protected.patch("/channels/{chid}")
def update_channel(chid: int, body: ChannelPatch, repo: Repo = Depends(get_repo)):
    ch = repo.channel(chid)
    if not ch:
        raise HTTPException(404, "채널을 찾을 수 없습니다.")
    f: dict = {}
    if body.url is not None:
        f["url"] = normalize_url(body.url)
        f["status"], f["status_msg"], f["feed_url"] = "pending", "주소가 변경되었습니다. 재시도로 확인하세요.", ""
    if body.type is not None:
        f["type"] = body.type
    if body.label is not None:
        f["label"] = body.label.strip()
    if body.active is not None:
        f["active"] = int(body.active)
    repo.update_channel(chid, **f)
    return repo.channel(chid)


@protected.delete("/channels/{chid}")
def delete_channel(chid: int, repo: Repo = Depends(get_repo)):
    if not repo.channel(chid):
        raise HTTPException(404, "채널을 찾을 수 없습니다.")
    repo.delete_channel(chid)
    return {"ok": True}


@protected.post("/channels/{chid}/retry")
def retry_channel(chid: int, repo: Repo = Depends(get_repo)):
    ch = repo.channel(chid)
    if not ch:
        raise HTTPException(404, "채널을 찾을 수 없습니다.")
    r = collect_channel(repo, ch)
    return {"result": r, "channel": repo.channel(chid)}


# ---------------- AI 질문 관리 ----------------
class QuestionIn(BaseModel):
    text: str = Field(min_length=2, max_length=200)
    categories: list[str] = Field(default_factory=list, max_length=6)
    enabled: bool = True
    panel: bool = False


class QuestionPatch(BaseModel):
    text: str | None = Field(default=None, min_length=2, max_length=200)
    categories: list[str] | None = Field(default=None, max_length=6)
    enabled: bool | None = None
    panel: bool | None = None


@protected.get("/questions")
def list_questions(repo: Repo = Depends(get_repo)):
    return views.build_questions(repo)


@protected.post("/questions")
def add_question(body: QuestionIn, repo: Repo = Depends(get_repo)):
    if len(repo.questions()) >= 500:
        raise HTTPException(400, "질문은 최대 500개입니다.")
    qid = repo.upsert_question({"text": body.text.strip(), "categories": _clean_list(body.categories, 20),
                                "enabled": body.enabled, "panel": body.panel})
    return next(q for q in repo.questions() if q["id"] == qid)


@protected.patch("/questions/{qid}")
def patch_question(qid: str, body: QuestionPatch, repo: Repo = Depends(get_repo)):
    cur = next((q for q in repo.questions() if q["id"] == qid), None)
    if not cur:
        raise HTTPException(404, "질문을 찾을 수 없습니다.")
    for k, v in body.model_dump(exclude_none=True).items():
        cur[k] = _clean_list(v, 20) if k == "categories" else (v.strip() if k == "text" else v)
    repo.upsert_question(cur)
    return next(q for q in repo.questions() if q["id"] == qid)


@protected.delete("/questions/{qid}")
def delete_question(qid: str, repo: Repo = Depends(get_repo)):
    repo.delete_question(qid)
    return {"ok": True}


# ---------------- AI 분석 ----------------
@protected.get("/analysis")
def get_analysis(kind: Literal["week", "month"] = "week", anchor: str | None = None, repo: Repo = Depends(get_repo)):
    check_date(anchor)
    return views.build_analysis(repo, kind, anchor)


class AnalysisIn(BaseModel):
    kind: Literal["week", "month"]
    anchor: str | None = None


@protected.post("/analysis")
def make_analysis(body: AnalysisIn, repo: Repo = Depends(get_repo)):
    return content_ai.generate_report(repo, body.kind, check_date(body.anchor), use_ai=True)


# ---------------- 설정 ----------------
class SettingsIn(BaseModel):
    goalTitle: str | None = Field(default=None, max_length=60)
    goalDesc: str | None = Field(default=None, max_length=200)
    runTime: str | None = None
    notifyTime: str | None = None
    autoAnalysis: bool | None = None
    engines: list[Literal["gemini", "chatgpt", "claude", "perplexity"]] | None = None
    dailyQuestions: int | None = Field(default=None, ge=1, le=150)
    includeTemplates: bool | None = None
    insightEngine: Literal["gemini", "chatgpt", "claude"] | None = None


@protected.get("/settings")
def get_settings(repo: Repo = Depends(get_repo)):
    return views.build_settings(repo)


@protected.put("/settings")
def put_settings(body: SettingsIn, request: Request, repo: Repo = Depends(get_repo)):
    goal, sched, aeo = repo.kv_get("goal", {}), repo.kv_get("schedule", {}), repo.kv_get("aeo", {})
    if body.goalTitle is not None:
        goal["title"] = body.goalTitle.strip()
    if body.goalDesc is not None:
        goal["desc"] = body.goalDesc.strip()
    for key, val in (("run_time", body.runTime), ("notify_time", body.notifyTime)):
        if val is not None:
            if not HHMM.match(val):
                raise HTTPException(400, "시각은 HH:MM 형식입니다.")
            sched[key] = val
    if body.autoAnalysis is not None:
        sched["auto_analysis"] = body.autoAnalysis
    if body.engines is not None:
        aeo["engines"] = body.engines
    if body.dailyQuestions is not None:
        aeo["daily_questions"] = body.dailyQuestions
    if body.includeTemplates is not None:
        aeo["include_templates"] = body.includeTemplates
    if body.insightEngine is not None:
        aeo["insight_engine"] = body.insightEngine
    repo.kv_set("goal", goal)
    repo.kv_set("schedule", sched)
    repo.kv_set("aeo", aeo)
    request.app.state.scheduler.reconfigure()
    return {"goal": goal, "schedule": sched, "aeo": aeo}


@protected.post("/goal/suggest")
def suggest_goal(repo: Repo = Depends(get_repo)):
    return {"suggestions": content_ai.suggest_goals(repo)}


# ---------------- 실행 / 작업 ----------------
class RunIn(BaseModel):
    kind: Literal["all", "content", "ai"] = "all"


@protected.post("/run")
def run_now(body: RunIn, request: Request):
    jid = request.app.state.jobs.start(body.kind, "manual")
    if jid is None:
        raise HTTPException(409, "이미 실행 중인 작업이 있습니다. 끝난 뒤 다시 시도하세요.")
    return {"job": jid}


@protected.get("/jobs/latest")
def latest_job(request: Request, repo: Repo = Depends(get_repo)):
    return {"job": repo.latest_job(), "running": request.app.state.jobs.running(), "recent": repo.recent_jobs(8)}


# ---------------- AI 언급 ----------------
@protected.get("/aeo/index")
def aeo_index(demo: bool = False, repo: Repo = Depends(get_repo)):
    return views.build_aeo_index(repo, demo)


@protected.get("/aeo/day/{date}")
def aeo_day(date: str, demo: bool = False, repo: Repo = Depends(get_repo)):
    check_date(date)
    p = views.build_aeo_day(repo, date, demo)
    if not p:
        raise HTTPException(404, "해당 날짜의 AI 언급 데이터가 없습니다.")
    return p


@protected.get("/aeo/{date}.xlsx")
def aeo_xlsx(date: str, demo: bool = False, repo: Repo = Depends(get_repo)):
    check_date(date)
    data = views.build_aeo_xlsx(repo, date, demo)
    if data is None:
        raise HTTPException(404, "해당 날짜의 측정이 없습니다.")
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="ai-mentions-{date}.xlsx"'})


# ---------------- 챗봇 ----------------
class ChatMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    messages: list[ChatMsg] = Field(min_length=1, max_length=20)


@protected.post("/chat")
def chat(body: ChatIn, repo: Repo = Depends(get_repo)):
    text, by = content_ai.answer_chat(repo, [m.model_dump() for m in body.messages])
    return {"answer": text, "by": by}


router.include_router(protected)
