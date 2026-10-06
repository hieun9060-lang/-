import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from aeo_monitor.server.app import create_app

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>
<item><title>숫자로 증명하는 합격 신화</title><link>http://x/p/1</link><pubDate>Sat, 04 Oct 2026 10:00:00 +0900</pubDate><description>의치한약수 입결 공개</description></item>
<item><title>=HYPERLINK("http://evil","click") 윈터스쿨 모집</title><link>http://x/p/2</link><pubDate>Sat, 04 Oct 2026 09:00:00 +0900</pubDate><description>접수</description></item>
<item><title>어제 올라온 급식 식단 안내</title><link>javascript:alert(1)</link><pubDate>Fri, 03 Oct 2026 09:00:00 +0900</pubDate><description>x</description></item>
</channel></rss>"""
H = {"X-Requested-With": "aeo-app"}


@pytest.fixture()
def feed_server(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "1")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            data = RSS.encode()
            self.send_response(200); self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/feed.xml"
    srv.shutdown()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct-horse-battery")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DISABLE_SCHEDULER", "1")
    app = create_app(tmp_path / "t.db", start_scheduler=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def authed(client):
    r = client.post("/api/login", json={"password": "correct-horse-battery"}, headers=H)
    assert r.status_code == 200
    client.headers.update(H)
    return client


def test_requires_login_and_csrf_header(client):
    assert client.get("/api/bootstrap").status_code == 401
    assert client.get("/api/me").json()["authenticated"] is False
    assert client.post("/api/login", json={"password": "correct-horse-battery"}).status_code == 403  # 헤더 없음
    assert client.post("/api/login", json={"password": "wrong"}, headers=H).status_code == 401
    assert client.post("/api/login", json={"password": "correct-horse-battery"}, headers=H).status_code == 200
    assert client.get("/api/bootstrap").status_code == 200
    # 로그인된 상태여도 변경 요청에 헤더가 없으면 거부 (CSRF)
    assert client.post("/api/run", json={"kind": "content"}).status_code == 403
    r = client.post("/api/logout", headers=H)
    assert client.get("/api/bootstrap").status_code == 401


def test_login_lockout(client):
    for _ in range(5):
        assert client.post("/api/login", json={"password": "nope"}, headers=H).status_code == 401
    r = client.post("/api/login", json={"password": "correct-horse-battery"}, headers=H)
    assert r.status_code == 429


def test_tampered_cookie_rejected(client):
    client.cookies.set("aeo_session", "forged.token.value")
    assert client.get("/api/bootstrap").status_code == 401


def test_requires_strong_secrets(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("APP_ALLOW_NO_AUTH", raising=False)
    with pytest.raises(RuntimeError):
        create_app(tmp_path / "t.db", start_scheduler=False)


def test_security_headers_and_static(client):
    r = client.get("/")
    assert r.status_code == 200 and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_bootstrap_seeded(authed):
    b = authed.get("/api/bootstrap").json()
    assert len(b["companies"]) == 14 and b["goal"]["title"] and b["schedule"]["run_time"] == "07:00"
    assert sum(c["role"] == "ours" for c in b["companies"]) == 1
    assert b["keys"]["gemini"] is False


def test_company_channel_flow_calendar_stats_evidence(authed, feed_server):
    ours = next(c for c in authed.get("/api/bootstrap").json()["companies"] if c["role"] == "ours")
    r = authed.post(f"/api/companies/{ours['id']}/channels", json={"url": feed_server})
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["item_count"] == 3
    assert authed.post(f"/api/companies/{ours['id']}/channels", json={"url": feed_server}).status_code == 409

    cal = authed.get("/api/calendar", params={"view": "day", "anchor": "2026-10-04"}).json()
    card = next(c for c in cal["companies"] if c["id"] == ours["id"])
    assert card["count"] == 2 and card["issue"] and card["summaryBy"] == "규칙"
    assert all(p["url"].startswith("http") or p["url"] == "" for p in card["posts"])
    # 채널이 없는 회사는 캘린더에 나오지 않음
    assert [c["id"] for c in cal["companies"]] == [ours["id"]]

    month = authed.get("/api/calendar", params={"view": "month", "anchor": "2026-10-15"}).json()
    assert month["daily"]["2026-10-04"][ours["id"]] == 2 and month["daily"]["2026-10-03"][ours["id"]] == 1

    st = authed.get("/api/stats", params={"range": "month", "anchor": "2026-10-15"}).json()
    assert st["total"] == 3 and st["graph"]["companies"][0]["total"] == 3 and st["graph"]["companies"][0]["series"][3] == 2

    ev = authed.get("/api/evidence", params={"days": "all", "q": "급식"}).json()
    assert ev["total"] == 1 and ev["items"][0]["url"] == ""  # javascript: 링크는 비움

    csv = authed.get("/api/evidence.csv").text
    assert "'=HYPERLINK" in csv and ",=HYPERLINK" not in csv  # 엑셀 수식 주입 방지


def test_ssrf_rejected_when_adding_channel(authed, monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
    ours = next(c for c in authed.get("/api/bootstrap").json()["companies"] if c["role"] == "ours")
    for url in ("http://127.0.0.1:8000/api/bootstrap", "http://169.254.169.254/latest/meta-data/", "file:///etc/passwd"):
        r = authed.post(f"/api/companies/{ours['id']}/channels", json={"url": url})
        assert r.status_code == 400, url


def test_company_crud_and_rules(authed, feed_server):
    r = authed.post("/api/companies", json={"name": "신규학원", "channels": [{"url": feed_server}]})
    assert r.status_code == 200 and r.json()["errors"] == [] and r.json()["company"]["channels"][0]["status"] == "ok"
    cid = r.json()["company"]["id"]
    assert authed.post("/api/companies", json={"name": "신규학원"}).status_code == 409
    assert authed.patch(f"/api/companies/{cid}", json={"role": "ours"}).status_code == 200
    comps = authed.get("/api/bootstrap").json()["companies"]
    assert [c["id"] for c in comps if c["role"] == "ours"] == [cid]  # 우리 회사는 하나
    assert authed.delete(f"/api/companies/{cid}").status_code == 400  # 우리 회사는 삭제 불가
    other = next(c["id"] for c in comps if c["id"] != cid)
    assert authed.delete(f"/api/companies/{other}").status_code == 200
    assert authed.patch("/api/companies/nope", json={"name": "x"}).status_code == 404
    assert authed.post("/api/companies", json={"name": "a" * 80}).status_code == 422


def test_job_digest_and_reports_without_ai_keys(authed, feed_server, client):
    ours = next(c for c in authed.get("/api/bootstrap").json()["companies"] if c["role"] == "ours")
    authed.post(f"/api/companies/{ours['id']}/channels", json={"url": feed_server})
    jobs = client.app.state.jobs
    jid = jobs.start("content", "manual", run_date="2026-10-04", sync=True)
    j = authed.get("/api/jobs/latest").json()["job"]
    assert j["id"] == jid and j["status"] == "done" and j["result"]["content"]["channels"] == 1
    cal = authed.get("/api/calendar", params={"view": "day", "anchor": "2026-10-04"}).json()
    assert cal["companies"][0]["summary"] and cal["companies"][0]["summaryBy"] == "규칙"
    r = authed.post("/api/summaries", json={"date": "2026-10-04"}).json()
    assert r["companies"] == 1
    rep = authed.post("/api/analysis", json={"kind": "week", "anchor": "2026-10-04"}).json()
    assert rep["headline"] and rep["sections"][0]["title"] == "한눈에 보기" and rep["stats"]["total"] == 3
    got = authed.get("/api/analysis", params={"kind": "week", "anchor": "2026-10-02"}).json()
    assert got["report"]["headline"] == rep["headline"]


def test_aeo_demo_run_and_endpoints(authed, client):
    from aeo_monitor.pipeline import run_aeo
    from aeo_monitor.repo import Repo
    from aeo_monitor.storage import Store
    store = Store(client.app.state.db_path)
    out = run_aeo(Repo(store), run_date="2026-10-04", engines_override=["mock"], limit=12)  # 하루 질문 수(10)가 우선
    store.close()
    assert out["questions"] == 10
    idx = authed.get("/api/aeo/index", params={"demo": True}).json()
    assert idx["latest"] == "2026-10-04"
    day = authed.get("/api/aeo/day/2026-10-04", params={"demo": True}).json()
    assert day["demo"] is True and day["actions"] and day["questions"]
    x = authed.get("/api/aeo/2026-10-04.xlsx", params={"demo": True})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert authed.get("/api/aeo/day/2026-10-09").status_code == 404


def test_settings_questions_chat(authed):
    r = authed.put("/api/settings", json={"goalTitle": "새 기준", "runTime": "06:30", "engines": ["gemini"], "dailyQuestions": 8})
    assert r.status_code == 200 and r.json()["schedule"]["run_time"] == "06:30" and r.json()["aeo"]["daily_questions"] == 8
    assert authed.put("/api/settings", json={"runTime": "25:99"}).status_code == 400
    q = authed.post("/api/questions", json={"text": "이천 기숙학원 후기 어때요", "panel": True}).json()
    assert authed.patch(f"/api/questions/{q['id']}", json={"enabled": False}).json()["enabled"] is False
    assert authed.delete(f"/api/questions/{q['id']}").status_code == 200
    g = authed.post("/api/goal/suggest").json()["suggestions"]
    assert len(g) == 3
    c = authed.post("/api/chat", json={"messages": [{"role": "user", "content": "요즘 경쟁사 동향은?"}]}).json()
    assert "키" in c["answer"]
    assert authed.post("/api/run", json={"kind": "bogus"}).status_code == 422


def test_store_usable_across_threads(tmp_path):
    """FastAPI 는 의존성과 핸들러를 서로 다른 스레드에서 실행할 수 있다."""
    from aeo_monitor.repo import Repo
    from aeo_monitor.storage import Store
    repo = Repo(Store(tmp_path / "t.db"))
    out = []
    t = threading.Thread(target=lambda: out.append(repo.companies()))
    t.start(); t.join()
    assert out == [[]]


def test_concurrent_requests(authed):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda i: authed.get("/api/stats", params={"range": "month"}).status_code, range(16)))
    assert set(codes) == {200}


def test_notification_markdown_and_scheduler_catch_up(authed, feed_server, client, monkeypatch):
    from datetime import datetime
    from aeo_monitor import pipeline
    from aeo_monitor.pipeline import notification_markdown
    from aeo_monitor.repo import Repo
    from aeo_monitor.server.scheduler import DailyScheduler
    from aeo_monitor.storage import Store

    ours = next(c for c in authed.get("/api/bootstrap").json()["companies"] if c["role"] == "ours")
    authed.post(f"/api/companies/{ours['id']}/channels", json={"url": feed_server})
    store = Store(client.app.state.db_path)
    title, md = notification_markdown(Repo(store))
    store.close()
    assert "모니터링" in title and "새 게시물" in md

    started = []

    class FakeJobs:
        def start(self, kind, trigger="manual", **kw):
            started.append((kind, trigger))
            return 1

    sched = DailyScheduler(client.app.state.db_path, FakeJobs())
    # 실행 시각(07:00) 이전이면 따라잡기 하지 않음
    monkeypatch.setattr("aeo_monitor.server.scheduler.now_kst", lambda: datetime(2026, 10, 6, 6, 0, tzinfo=__import__("aeo_monitor.timeutil", fromlist=["KST"]).KST))
    sched.catch_up()
    assert started == []
    # 시각이 지났고 오늘 실행 기록이 없으면 실행
    monkeypatch.setattr("aeo_monitor.server.scheduler.now_kst", lambda: datetime(2026, 10, 6, 9, 30, tzinfo=__import__("aeo_monitor.timeutil", fromlist=["KST"]).KST))
    monkeypatch.setattr("aeo_monitor.server.scheduler.today_kst", lambda: "2026-10-06")
    sched.catch_up()
    assert started == [("all", "catchup")]
    # 오늘 이미 실행했다면 다시 하지 않음
    store = Store(client.app.state.db_path)
    repo = Repo(store)
    jid = repo.create_job("all", "schedule")
    store.conn.execute("UPDATE jobs SET started_at='2026-10-06T07:00:00+09:00' WHERE id=?", (jid,))
    repo.update_job(jid, status="done")
    store.close()
    sched.catch_up()
    assert started == [("all", "catchup")]


def test_scheduler_registers_daily_jobs(client):
    sched = client.app.state.scheduler
    sched.reconfigure()
    ids = {j.id for j in sched.sched.get_jobs()}
    assert ids == {"daily-run", "daily-notify"}


def test_ai_flows_parse_model_output(authed, feed_server, client, monkeypatch):
    """LLM 응답(JSON)을 파싱해 요약·분석·추천에 반영하고, 형식이 깨지면 규칙 기반으로 대체한다."""
    import json as _json
    from aeo_monitor import llm
    ours = next(c for c in authed.get("/api/bootstrap").json()["companies"] if c["role"] == "ours")
    authed.post(f"/api/companies/{ours['id']}/channels", json={"url": feed_server})
    prompts = []

    def fake(prompt, system, prefer="gemini", models=None):
        prompts.append(prompt)
        if "companies" in prompt and "중심 이슈" in prompt:
            cid = _json.loads(prompt.split("<data>")[1].split("</data>")[0])[0]["id"]
            return "```json\n" + _json.dumps({"companies": [{"id": cid, "issue": "합격 홍보", "summary": "합격 신화 콘텐츠 중심.", "highlight": "입결 공개"}]}) + "\n```", "Gemini"
        if '"headline"' in prompt:
            return _json.dumps({"headline": "AI가 쓴 결론", "sections": [{"title": "한눈에 보기", "bullets": ["총 3건"]}]}), "Gemini"
        if "리서치 기준 3개" in prompt:
            return _json.dumps([{"title": "추천1", "desc": "설명1"}]), "Gemini"
        return "챗봇 답변입니다.", "Gemini"

    monkeypatch.setattr(llm, "complete", fake)
    authed.post("/api/summaries", json={"date": "2026-10-04"})
    card = authed.get("/api/calendar", params={"view": "day", "anchor": "2026-10-04"}).json()["companies"][0]
    assert card["issue"] == "합격 홍보" and card["summaryBy"] == "Gemini" and "<data>" in prompts[0]
    rep = authed.post("/api/analysis", json={"kind": "week", "anchor": "2026-10-04"}).json()
    assert rep["headline"] == "AI가 쓴 결론" and rep["model"] == "Gemini"
    assert authed.post("/api/goal/suggest").json()["suggestions"][0]["title"] == "추천1"
    assert authed.post("/api/chat", json={"messages": [{"role": "user", "content": "질문"}]}).json()["answer"] == "챗봇 답변입니다."

    # 모델이 JSON 이 아닌 말을 하면 규칙 기반으로 대체
    monkeypatch.setattr(llm, "complete", lambda *a, **k: ("죄송하지만 형식을 못 지키겠습니다.", "Gemini"))
    authed.post("/api/summaries", json={"date": "2026-10-04"})
    card = authed.get("/api/calendar", params={"view": "day", "anchor": "2026-10-04"}).json()["companies"][0]
    assert card["summaryBy"] == "규칙"
    assert authed.post("/api/analysis", json={"kind": "week", "anchor": "2026-10-04"}).json()["model"] == "규칙"
