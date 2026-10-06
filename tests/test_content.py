import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aeo_monitor.content import collectors
from aeo_monitor.content.fetch import FetchError, check_public_url, safe_get

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>
<item><title>숫자로 증명하는 합격 신화</title><link>http://{host}/p/1</link><pubDate>Sat, 04 Oct 2026 10:00:00 +0900</pubDate>
<description>&lt;p&gt;의치한약수 입결 &lt;b&gt;공개&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>2027 윈터스쿨 모집 안내</title><link>http://{host}/p/2</link><pubDate>Fri, 03 Oct 2026 09:00:00 +0900</pubDate><description>접수 시작</description></item>
</channel></rss>"""
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>yt</title>
<entry><title>[D-50] 보노스프 이벤트</title><link rel="alternate" href="http://{host}/watch?v=a"/><updated>2026-10-04T01:00:00+00:00</updated>
<summary>영상 설명</summary></entry></feed>"""
HOME = """<html><body><nav><a href="/menu">메뉴 메뉴 메뉴</a></nav><a href="/notice/1">2027 윈터스쿨 접수 안내드립니다</a>
<a href="/notice/2">합격 수기 공개 이벤트 진행</a><a href="/login">로그인</a><a href="http://other.com/x">외부 링크 텍스트 길게</a></body></html>"""
HOME_RSS = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head><body>hi</body></html>'


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "1")
    state = {"home_links": HOME}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            host = self.headers["Host"]
            routes = {
                "/rss.xml": ("application/rss+xml", RSS.format(host=host)),
                "/atom.xml": ("application/atom+xml", ATOM.format(host=host)),
                "/home": ("text/html; charset=utf-8", state["home_links"]),
                "/withfeed": ("text/html", HOME_RSS),
                "/feed.xml": ("application/rss+xml", RSS.format(host=host)),
            }
            if self.path == "/private":
                self.send_response(403); self.end_headers(); return
            if self.path == "/redir":
                self.send_response(302); self.send_header("Location", "/rss.xml"); self.end_headers(); return
            if self.path in routes:
                ct, body = routes[self.path]
                data = body.encode()
                self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data)
            else:
                self.send_response(404); self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}", state
    srv.shutdown()


def test_detect_type():
    assert collectors.detect_type("https://www.youtube.com/@abc") == "youtube"
    assert collectors.detect_type("https://blog.naver.com/abc") == "blog"
    assert collectors.detect_type("https://x.tistory.com") == "blog"
    assert collectors.detect_type("https://site.com/rss.xml") == "rss"
    assert collectors.detect_type("https://academy.com/") == "homepage"


def test_naver_blog_id():
    f = collectors._naver_blog_id
    assert f("https://blog.naver.com/etoos_icheon") == "etoos_icheon"
    assert f("https://m.blog.naver.com/abc/223") == "abc"
    assert f("https://blog.naver.com/PostList.naver?blogId=xyz") == "xyz"
    assert f("https://example.com/abc") is None


def test_rss_collect(server):
    base, _ = server
    r = collectors.collect(f"{base}/rss.xml")
    assert r.status == "ok" and len(r.items) == 2 and not r.homepage_mode
    assert r.items[0].title == "숫자로 증명하는 합격 신화"
    assert "의치한약수 입결 공개" in r.items[0].body and "<" not in r.items[0].body
    assert r.items[0].published.strftime("%Y-%m-%d") == "2026-10-04"


def test_atom_and_redirect_and_discovered_feed(server):
    base, _ = server
    assert collectors.collect(f"{base}/atom.xml").items[0].published.strftime("%Y-%m-%d") == "2026-10-04"
    assert len(collectors.collect(f"{base}/redir").items) == 2
    r = collectors.collect(f"{base}/withfeed")
    assert len(r.items) == 2 and r.feed_url.endswith("/feed.xml")


def test_homepage_mode_and_baseline(server, tmp_path):
    base, state = server
    from aeo_monitor.repo import Repo
    from aeo_monitor.storage import Store
    repo = Repo(Store(tmp_path / "t.db"))
    repo.create_company({"id": "a", "name": "A", "role": "ours"})
    chid = repo.add_channel("a", "homepage", f"{base}/home")
    ch = repo.channel(chid)
    r1 = collectors.collect_channel(repo, ch)
    assert r1["new"] == 2 and r1["status"] == "ok"
    # 첫 수집분은 baseline → 캘린더/통계에 나오지 않음
    assert repo.posts("2000-01-01", "2100-01-01") == []
    state["home_links"] = HOME.replace("</body>", '<a href="/notice/3">새로 올라온 공지 게시물 제목</a></body>')
    r2 = collectors.collect_channel(repo, ch)
    assert r2["new"] == 1
    posts = repo.posts("2000-01-01", "2100-01-01")
    assert [p["title"] for p in posts] == ["새로 올라온 공지 게시물 제목"]


def test_login_status_and_404(server):
    base, _ = server
    r = collectors.collect(f"{base}/private")
    assert r.status == "login" and "로그인" in r.message
    assert collectors.collect(f"{base}/nope").status == "error"


def test_rss_channel_stores_posts_with_topic_and_dates(server, tmp_path):
    base, _ = server
    from aeo_monitor.repo import Repo
    from aeo_monitor.storage import Store
    repo = Repo(Store(tmp_path / "t.db"))
    repo.create_company({"id": "a", "name": "A", "role": "ours"})
    ch = repo.channel(repo.add_channel("a", "rss", f"{base}/rss.xml"))
    assert collectors.collect_channel(repo, ch)["new"] == 2
    assert collectors.collect_channel(repo, ch)["new"] == 0  # 중복 없음
    posts = {p["title"]: p for p in repo.posts("2026-10-01", "2026-10-31")}
    assert posts["숫자로 증명하는 합격 신화"]["topic"] == "합격 실적" and posts["숫자로 증명하는 합격 신화"]["post_date"] == "2026-10-04"
    assert posts["2027 윈터스쿨 모집 안내"]["topic"] == "모집·일정"
    assert repo.channel(ch["id"])["status"] == "ok" and repo.channel(ch["id"])["item_count"] == 2


def test_youtube_feed_resolution(monkeypatch):
    f = collectors._youtube_feed
    assert f("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv")[0].endswith("channel_id=UCabcdefghijklmnopqrstuv")
    assert f("https://www.youtube.com/playlist?list=PL123")[0].endswith("playlist_id=PL123")
    html = '<html>..."channelId":"UCzzzzzzzzzzzzzzzzzzzzzz"...</html>'

    class P:
        text = html
    monkeypatch.setattr(collectors, "safe_get", lambda *a, **k: P())
    assert f("https://www.youtube.com/@abc")[0].endswith("channel_id=UCzzzzzzzzzzzzzzzzzzzzzz")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://localhost/x", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/",
    "http://192.168.1.1/", "http://[::1]/", "file:///etc/passwd", "ftp://example.com/", "http://user:pw@example.com/",
    "http://0.0.0.0/",
])
def test_ssrf_blocked(url, monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
    with pytest.raises(FetchError):
        check_public_url(url)


def test_redirect_to_private_blocked(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_FETCH", raising=False)
    import aeo_monitor.content.fetch as fx

    class R:
        status_code = 302
        headers = {"location": "http://169.254.169.254/"}

        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(fx, "check_public_url", lambda u: (_ for _ in ()).throw(FetchError("blocked", "blocked")) if "169.254" in u else None)
    monkeypatch.setattr(fx.requests, "get", lambda *a, **k: R())
    with pytest.raises(FetchError):
        safe_get("http://example.com/")
