"""채널(블로그·유튜브·홈페이지·RSS)에서 새 게시물을 수집한다.

- 네이버 블로그 → rss.blog.naver.com/<id>.xml
- 티스토리 → /rss
- 유튜브 → channel_id 를 찾아 youtube.com/feeds/videos.xml
- 그 밖의 주소 → 페이지의 RSS/Atom 링크, 없으면 '홈페이지' 방식(페이지 링크 목록의 변화 추적)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

import feedparser
from bs4 import BeautifulSoup

from ..timeutil import KST, now_kst
from .classify import classify
from .fetch import FetchError, Fetched, safe_get

MAX_ITEMS = 40  # 채널당 한 번에 읽는 최대 항목


@dataclass
class Item:
    url: str
    title: str
    snippet: str = ""
    body: str = ""
    published: datetime | None = None


@dataclass
class CollectResult:
    items: list[Item] = field(default_factory=list)
    feed_url: str = ""
    platform: str = ""
    status: str = "ok"  # ok | warn | login | error
    message: str = ""
    homepage_mode: bool = False


# ---------- 유형 판별 ----------
def detect_type(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    if h.endswith("youtube.com") or h == "youtu.be":
        return "youtube"
    if h.endswith("blog.naver.com") or h.endswith("tistory.com") or h.endswith("brunch.co.kr") or h.endswith("velog.io"):
        return "blog"
    if urlparse(url).path.lower().endswith((".xml", ".rss", ".atom")) or "/feed" in url.lower() or "/rss" in url.lower():
        return "rss"
    return "homepage"


def _naver_blog_id(url: str) -> str | None:
    p = urlparse(url)
    h = (p.hostname or "").lower()
    if h in ("blog.naver.com", "m.blog.naver.com"):
        q = parse_qs(p.query)
        if q.get("blogId"):
            return q["blogId"][0]
        parts = [x for x in p.path.split("/") if x]
        if parts and parts[0] not in ("PostList.naver", "PostView.naver", "PostView.nhn", "PostList.nhn"):
            return parts[0]
    if h == "rss.blog.naver.com":
        m = re.match(r"^/([^/.]+)\.xml", p.path)
        return m.group(1) if m else None
    return None


def _clean_text(html: str, limit: int = 4000) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def _entry_dt(e) -> datetime | None:
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(e, k, None) or (e.get(k) if hasattr(e, "get") else None)
        if t:
            try:
                from calendar import timegm
                return datetime.fromtimestamp(timegm(t), tz=KST)
            except (ValueError, OverflowError, TypeError):
                continue
    return None


# ---------- 피드 ----------
def parse_feed(content: bytes | str, base_url: str = "") -> list[Item]:
    d = feedparser.parse(content)
    items: list[Item] = []
    for e in d.entries[:MAX_ITEMS]:
        link = e.get("link") or ""
        if base_url and link:
            link = urljoin(base_url, link)
        if not link:
            continue
        body_html = ""
        if e.get("content"):
            body_html = e["content"][0].get("value", "")
        body_html = body_html or e.get("summary", "") or e.get("description", "")
        body = _clean_text(body_html)
        title = _clean_text(e.get("title", ""), 300) or "(제목 없음)"
        items.append(Item(url=link, title=title, snippet=body[:240], body=body, published=_entry_dt(e)))
    return items


def _find_feed_links(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for l in soup.find_all("link", attrs={"rel": re.compile("alternate", re.I)}):
        t = (l.get("type") or "").lower()
        if ("rss" in t or "atom" in t) and l.get("href"):
            out.append(urljoin(base, l["href"]))
    return out


def _youtube_feed(url: str) -> tuple[str, str]:
    """(피드 주소, 채널명 힌트)."""
    p = urlparse(url)
    q = parse_qs(p.query)
    if "list" in q and p.path.startswith("/playlist"):
        return f"https://www.youtube.com/feeds/videos.xml?playlist_id={q['list'][0]}", ""
    m = re.match(r"^/channel/(UC[\w-]{20,})", p.path)
    if m:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}", ""
    page = safe_get(url, headers={"Cookie": "CONSENT=YES+1; SOCS=CAI"})
    html = page.text
    for pat in (r'"channelId":"(UC[\w-]{20,})"', r'"externalId":"(UC[\w-]{20,})"',
                r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{20,})"',
                r'channel_id=(UC[\w-]{20,})'):
        mm = re.search(pat, html)
        if mm:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={mm.group(1)}", ""
    raise FetchError("유튜브 채널 ID를 찾지 못했습니다. 채널 주소(youtube.com/@이름 또는 /channel/UC…)를 확인하세요.")


# ---------- 홈페이지(링크 목록 추적) ----------
_SKIP_TEXT = re.compile(r"^(로그인|회원가입|홈|home|menu|메뉴|더보기|more|top|맨위로|이전|다음|prev|next|\d+)$", re.I)


def extract_page_items(html: str, base: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    host = (urlparse(base).hostname or "").lower()
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        link = urljoin(base, href).split("#")[0]
        if (urlparse(link).hostname or "").lower() != host or link.rstrip("/") == base.rstrip("/"):
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(text) < 6 or _SKIP_TEXT.match(text) or link in seen:
            continue
        seen.add(link)
        items.append(Item(url=link, title=text[:200]))
        if len(items) >= MAX_ITEMS:
            break
    return items


def collect(url: str, type_hint: str = "") -> CollectResult:
    """한 채널의 항목을 가져온다. 예외 대신 status/message 로 결과를 돌려준다."""
    typ = type_hint or detect_type(url)
    res = CollectResult(platform=typ)
    try:
        feed_url = ""
        if typ == "youtube":
            feed_url, _ = _youtube_feed(url)
        else:
            bid = _naver_blog_id(url)
            host = (urlparse(url).hostname or "").lower()
            if bid:
                feed_url = f"https://rss.blog.naver.com/{bid}.xml"
            elif host.endswith(".tistory.com") and not urlparse(url).path.lower().endswith(("rss", ".xml")):
                feed_url = f"https://{host}/rss"
        page: Fetched | None = None
        if not feed_url:
            page = safe_get(url)
            ct = page.content_type.lower()
            head = page.content[:600].lstrip().lower()
            if "xml" in ct or head.startswith(b"<?xml") or head.startswith(b"<rss") or head.startswith(b"<feed"):
                feed_url = page.url
            else:
                links = _find_feed_links(page.text, page.url)
                feed_url = links[0] if links else ""
        if feed_url:
            fp = page if (page and feed_url == page.url) else safe_get(feed_url)
            res.items = parse_feed(fp.content, fp.url)
            res.feed_url = feed_url
            if not res.items:
                res.status, res.message = "warn", "피드는 열렸지만 게시물을 찾지 못했습니다."
            else:
                res.message = f"구조화된 항목 {len(res.items)}개를 수집했습니다."
            return res
        # RSS 가 없으면 페이지 링크 추적
        page = page or safe_get(url)
        res.items = extract_page_items(page.text, page.url)
        res.homepage_mode = True
        res.platform = "homepage" if typ in ("homepage", "rss", "") else typ
        if not res.items:
            res.status, res.message = "warn", "페이지에서 게시물 링크를 찾지 못했습니다. (로그인·자바스크립트로 그려지는 페이지일 수 있습니다)"
        else:
            res.message = f"페이지 링크 {len(res.items)}개를 확인했습니다."
    except FetchError as e:
        res.status = "login" if e.kind == "login" else "error"
        res.message = str(e)
    except Exception as e:  # noqa: BLE001 - 한 채널의 예기치 못한 오류가 전체 수집을 멈추지 않도록
        res.status, res.message = "error", f"수집 중 오류: {type(e).__name__}: {str(e)[:120]}"
    return res


def collect_channel(repo, channel: dict) -> dict:
    """채널 하나를 수집해 DB에 반영. {'new': n, 'status': ..., 'message': ...}"""
    cid = channel["company_id"]
    res = collect(channel["url"], channel["type"])
    now = now_kst().isoformat(timespec="seconds")
    new = 0
    if res.items:
        first_homepage_run = res.homepage_mode and repo.post_count(channel["id"]) == 0
        for it in res.items:
            if it.published:
                pub = it.published.isoformat(timespec="seconds")
                post_date = it.published.astimezone(KST).strftime("%Y-%m-%d")
            else:
                pub, post_date = None, now_kst().strftime("%Y-%m-%d")
            if repo.upsert_post(company_id=cid, channel_id=channel["id"], platform=res.platform or channel["type"],
                                url=it.url, title=it.title, snippet=it.snippet, body=it.body,
                                topic=classify(it.title, it.body), published_at=pub, post_date=post_date,
                                baseline=first_homepage_run):
                new += 1
        repo.conn.commit()
    fields = {"status": res.status, "status_msg": res.message, "last_checked_at": now, "feed_url": res.feed_url}
    if res.status in ("ok", "warn") and res.items:
        fields["last_success_at"] = now
        fields["item_count"] = repo.post_count(channel["id"])
    repo.update_channel(channel["id"], **fields)
    return {"new": new, "status": res.status, "message": res.message}


def collect_all(repo, progress=None) -> dict:
    """활성 회사의 활성 채널 전체."""
    active = {c["id"] for c in repo.companies()}
    chans = [c for c in repo.channels(active_only=True) if c["company_id"] in active]
    total_new, bad = 0, 0
    for i, ch in enumerate(chans, 1):
        if progress:
            progress(f"채널 수집 {i}/{len(chans)}")
        r = collect_channel(repo, ch)
        total_new += r["new"]
        bad += r["status"] in ("login", "error")
    return {"channels": len(chans), "new_posts": total_new, "problem_channels": bad}
