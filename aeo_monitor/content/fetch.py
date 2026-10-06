"""외부 주소 안전 수집 (SSRF 방지).

사용자가 입력한 URL 을 서버가 대신 열기 때문에
- http/https 만 허용, 사용자정보(user:pass@) 금지
- 이름 해석 결과가 사설·루프백·링크로컬·예약 대역이면 차단 (매 리다이렉트마다 재검사)
- 리다이렉트 횟수·응답 크기·시간 제한
테스트에서만 ALLOW_PRIVATE_FETCH=1 로 로컬 서버 접근을 허용합니다.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests

UA = "Mozilla/5.0 (compatible; AcademyMonitor/1.0; +research)"
MAX_BYTES = 3_000_000
TIMEOUT = 20


class FetchError(Exception):
    def __init__(self, msg: str, kind: str = "error"):
        super().__init__(msg)
        self.kind = kind  # error | login | blocked


@dataclass
class Fetched:
    url: str
    status: int
    content: bytes
    content_type: str

    @property
    def text(self) -> str:
        enc = None
        ct = self.content_type.lower()
        if "charset=" in ct:
            enc = ct.split("charset=")[1].split(";")[0].strip()
        for e in ([enc] if enc else []) + ["utf-8", "euc-kr", "cp949"]:
            try:
                return self.content.decode(e)
            except (UnicodeDecodeError, LookupError):
                continue
        return self.content.decode("utf-8", errors="replace")


def _allow_private() -> bool:
    return os.environ.get("ALLOW_PRIVATE_FETCH") == "1"


def check_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchError("http/https 주소만 사용할 수 있습니다.", "blocked")
    if not p.hostname or p.username or p.password:
        raise FetchError("주소 형식이 올바르지 않습니다.", "blocked")
    if _allow_private():
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchError(f"주소를 찾을 수 없습니다: {p.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
                or ip.is_unspecified or (ip.version == 6 and ip.ipv4_mapped and ip.ipv4_mapped.is_private)):
            raise FetchError("내부망 주소는 수집할 수 없습니다.", "blocked")


def safe_get(url: str, *, max_redirects: int = 4, timeout: int = TIMEOUT, max_bytes: int = MAX_BYTES,
             headers: dict | None = None) -> Fetched:
    hdrs = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9"}
    hdrs.update(headers or {})
    cur = url
    for _ in range(max_redirects + 1):
        check_public_url(cur)
        try:
            with requests.get(cur, headers=hdrs, timeout=timeout, allow_redirects=False, stream=True) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    cur = urljoin(cur, r.headers["location"])
                    continue
                if r.status_code in (401, 403):
                    raise FetchError(f"접근이 거부되었습니다 (HTTP {r.status_code}). 로그인이 필요하거나 수집이 차단된 페이지입니다.", "login")
                if r.status_code == 404:
                    raise FetchError("페이지를 찾을 수 없습니다 (HTTP 404).")
                if r.status_code >= 400:
                    raise FetchError(f"서버 오류 (HTTP {r.status_code}).")
                buf = bytearray()
                for chunk in r.iter_content(65536):
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        break
                return Fetched(cur, r.status_code, bytes(buf[:max_bytes]), r.headers.get("content-type", ""))
        except requests.RequestException as e:
            raise FetchError(f"연결 실패: {type(e).__name__}") from e
    raise FetchError("리다이렉트가 너무 많습니다.")
