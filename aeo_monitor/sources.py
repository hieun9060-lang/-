"""출처 URL을 사이트 유형으로 분류."""
from __future__ import annotations

from urllib.parse import unquote, urlparse

from .config import BrandConfig

OFFICIAL = "공식 홈페이지(이천캠퍼스)"
COMPETITOR = "경쟁사 공식자료"


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


class SourceClassifier:
    def __init__(self, rules: dict, brands: BrandConfig):
        self.types = rules.get("types", [])
        self.default = rules.get("default", "기타/무관")
        self.order = rules.get("order", [])
        self.brands = brands

    def classify(self, url: str, title: str = "") -> str:
        u = unquote(url or "").lower()
        title_l = (title or "").lower()
        target = self.brands.target
        if any(d.lower() in u for d in target.domains if d):
            return OFFICIAL
        for b in self.brands.competitors:
            if b.group == target.group and b.group:
                continue  # 같은 이투스 계열 타 캠퍼스는 아래 '자사' 규칙으로
            if any(d.lower() in u for d in b.domains if d):
                return COMPETITOR
        for t in self.types:
            if any(m.lower() in u for m in t.get("match", [])):
                req = t.get("require_any")
                if req and not any(r.lower() in u or r.lower() in title_l for r in req):
                    continue
                return t["name"]
        return self.default

    def resolve(self, url: str, title: str = "") -> tuple[str, str]:
        """(분류용 URL, 도메인). Gemini 그라운딩은 리다이렉트 URL + 도메인 제목으로 오므로 제목을 사용."""
        if domain_of(url) in REDIRECT_HOSTS and title and " " not in title.strip():
            real = "https://" + title.strip()
            return real, domain_of(real)
        return url, domain_of(url)

    def ordered_types(self, present: set[str]) -> list[str]:
        known = [t for t in self.order if t in present]
        return known + sorted(present - set(known))


REDIRECT_HOSTS = {"vertexaisearch.cloud.google.com"}
