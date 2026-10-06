import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from aeo_monitor import config
from aeo_monitor.cli import main
from aeo_monitor.timeutil import today_kst

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>2027 윈터스쿨 모집 설명회 안내</title><link>http://x/p/1</link><pubDate>{d} 09:00:00 +0900</pubDate><description>접수 시작</description></item>
<item><title>합격 수기 공개</title><link>http://x/p/2</link><pubDate>{d} 08:00:00 +0900</pubDate><description>합격 후기</description></item></channel></rss>"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    shutil.copytree(config.CONFIG_DIR, cfg)
    monkeypatch.setattr(config, "CONFIG_DIR", cfg)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "")  # 비어 있으면 '키 없음'
    from email.utils import formatdate
    body = RSS.format(d=formatdate(usegmt=False).rsplit(" ", 1)[0].replace(",", ",")).encode()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (cfg / "monitor.yaml").write_text(f"channels:\n  etoos247_icheon:\n    - http://127.0.0.1:{srv.server_port}/feed.xml\n", encoding="utf-8")
    yield tmp_path
    srv.shutdown()


def test_build_site_end_to_end(env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-VALUE-123")  # 산출물에 키가 새면 안 됨 (실제 호출은 막힘: 네트워크 없음)
    monkeypatch.setattr("aeo_monitor.llm.complete", lambda *a, **k: ("", ""))
    monkeypatch.setattr("aeo_monitor.pipeline.build_engines", lambda *a, **k: [])  # 실제 AI 호출 방지
    out = env / "site"
    assert main(["build-site", "--out", str(out), "--repo", "me/repo", "--branch", "main"]) == 0
    assert (out / "index.html").exists() and (out / "static/app.css").exists() and (out / "_headers").exists()
    assert "STATIC = true" in (out / "static/js/mode.js").read_text(encoding="utf-8")
    assert '"repo": "me/repo"' in (out / "static/js/mode.js").read_text(encoding="utf-8")

    boot = json.loads((out / "data/bootstrap.json").read_text(encoding="utf-8"))
    assert boot["static"] is True and boot["job"]["status"] == "done" and len(boot["companies"]) == 14
    ours = next(c for c in boot["companies"] if c["role"] == "ours")
    assert ours["channels"][0]["status"] == "ok" and ours["posts"] == 2

    t = today_kst()
    day = json.loads((out / f"data/calendar/day/{t}.json").read_text(encoding="utf-8"))
    assert day["hasChannels"] and day["companies"][0]["count"] == 2 and day["companies"][0]["posts"][0]["url"].startswith("http")
    assert (out / f"data/stats/month/all/{t[:8]}01.json").exists() and (out / f"data/stats/year/youtube/{t[:4]}-01-01.json").exists()
    posts = json.loads((out / "data/posts.json").read_text(encoding="utf-8"))
    assert len(posts["items"]) == 2 and "합격 실적" in posts["topics"]
    wk = list((out / "data/analysis/week").glob("*.json")) + list((out / "data/analysis/month").glob("*.json"))
    assert len(wk) >= 2  # 이번 주·이번 달 분석이 만들어짐
    for f in ("questions", "settings", "chat-context", "meta"):
        assert (out / f"data/{f}.json").exists()

    # 키·DB 파일이 산출물에 들어가지 않음
    for p in out.rglob("*"):
        if p.is_file():
            assert p.suffix not in (".db", ".yaml"), p
            if p.suffix in (".json", ".js", ".html"):
                assert "SECRET-KEY-VALUE-123" not in p.read_text(encoding="utf-8", errors="ignore"), p
    # DB 는 WAL 없이 파일 하나로 남음 (데이터 보관용)
    assert (env / "data/aeo.db").exists() and not (env / "data/aeo.db-wal").exists()


def test_build_site_reports_config_error(env, capsys):
    (config.CONFIG_DIR / "monitor.yaml").write_text("channels:\n  a: [\n", encoding="utf-8")
    assert main(["build-site", "--out", str(env / "site"), "--skip-collect"]) == 2
    assert not (env / "site").exists()


def test_second_run_keeps_history_and_dedupes(env):
    out = env / "site"
    main(["build-site", "--out", str(out)])
    main(["build-site", "--out", str(out)])
    posts = json.loads((out / "data/posts.json").read_text(encoding="utf-8"))
    assert len(posts["items"]) == 2
    boot = json.loads((out / "data/bootstrap.json").read_text(encoding="utf-8"))
    assert boot["job"]["id"] == 2


def test_static_matches_server_api(env, monkeypatch):
    """정적 JSON 과 서버 API 응답이 같은 값인지 (같은 views 함수를 쓰므로 어긋나면 안 된다)."""
    from fastapi.testclient import TestClient
    from aeo_monitor.server.app import create_app
    out = env / "site"
    main(["build-site", "--out", str(out)])
    monkeypatch.setenv("APP_ALLOW_NO_AUTH", "1")
    with TestClient(create_app(config.DATA_DIR / "aeo.db", start_scheduler=False)) as c:
        t = today_kst()
        api = c.get("/api/calendar", params={"view": "day", "anchor": t}).json()
        assert api == json.loads((out / f"data/calendar/day/{t}.json").read_text(encoding="utf-8"))
        api = c.get("/api/stats", params={"range": "month", "anchor": t, "platform": "blog"}).json()
        st = json.loads((out / f"data/stats/month/blog/{t[:8]}01.json").read_text(encoding="utf-8"))
        assert {k: v for k, v in api.items() if k != "anchor"} == {k: v for k, v in st.items() if k != "anchor"}


def test_workflow_is_valid_and_scheduled_daily():
    import yaml
    wf = yaml.safe_load((Path(__file__).resolve().parent.parent / ".github/workflows/monitor.yml").read_text(encoding="utf-8"))
    on = wf.get("on") or wf[True]  # PyYAML 은 'on' 을 True 로 읽는다
    assert [c["cron"] for c in on["schedule"]] == ["0 22 * * *", "0 0 * * *"]  # 07:00 / 09:00 KST
    assert set(wf["jobs"]) == {"collect", "notify"}
    assert wf["concurrency"]["cancel-in-progress"] is False and "config/**" in on["push"]["paths"]
    steps = " ".join(str(s.get("run", "")) + str(s.get("uses", "")) for s in wf["jobs"]["collect"]["steps"])
    assert "build-site" in steps and "data-store" in steps and "wrangler-action" in steps


def test_cloudflare_functions():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node 가 없습니다")
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([node, "--test", str(root / "functions/test/functions.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
