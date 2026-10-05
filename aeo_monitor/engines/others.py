"""ChatGPT(OpenAI), Gemini, Perplexity — 각 사의 웹검색 기반 답변 API (REST).

API 키가 설정된 엔진만 실행됩니다. 모델명은 환경변수로 바꿀 수 있습니다.
응답 형식이 바뀌어도 죽지 않도록 방어적으로 파싱합니다.
"""
from __future__ import annotations

import os

import requests

from .base import SYSTEM_PROMPT, Citation, Engine, EngineResult, dedupe

TIMEOUT = 180


def _post(url: str, retries: int = 5, **kw) -> requests.Response:
    """429(호출 한도)·5xx 는 지수 백오프로 재시도."""
    import time
    for attempt in range(retries + 1):
        resp = requests.post(url, timeout=TIMEOUT, **kw)
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
            resp.raise_for_status()
            return resp
        wait = float(resp.headers.get("retry-after") or 0) or min(60, 2 ** (attempt + 2))
        time.sleep(wait)
    raise RuntimeError("unreachable")


class OpenAIEngine(Engine):
    name = "chatgpt"
    default_model = os.environ.get("OPENAI_MODEL", "gpt-5")

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def ask(self, question: str) -> EngineResult:
        r = EngineResult(self.name, self.model)
        try:
            resp = requests.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                json={
                    "model": self.model,
                    "instructions": SYSTEM_PROMPT,
                    "input": question,
                    "tools": [{"type": "web_search", "user_location": {"type": "approximate", "country": "KR"}}],
                    "include": ["web_search_call.action.sources"],
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            r.error = f"openai: {e}"
            return r
        texts, cites = [], []
        for item in data.get("output", []) or []:
            if item.get("type") == "message":
                for part in item.get("content", []) or []:
                    if part.get("type") == "output_text":
                        texts.append(part.get("text", ""))
                        for a in part.get("annotations", []) or []:
                            if a.get("type") == "url_citation" and a.get("url"):
                                cites.append(Citation(a["url"], a.get("title", ""), "", True))
            elif item.get("type") == "web_search_call":
                for s in ((item.get("action") or {}).get("sources") or []):
                    if s.get("url"):
                        cites.append(Citation(s["url"], s.get("title", "")))
        r.answer = "".join(texts).strip()
        r.citations = dedupe(cites)
        return r


class GeminiEngine(Engine):
    name = "gemini"
    default_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY"))

    def ask(self, question: str) -> EngineResult:
        r = EngineResult(self.name, self.model)
        try:
            resp = _post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [{"role": "user", "parts": [{"text": question}]}],
                    "tools": [{"google_search": {}}],
                },
            )
            data = resp.json()
        except requests.RequestException as e:
            r.error = f"gemini: {e}"
            return r
        cand = (data.get("candidates") or [{}])[0]
        r.answer = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) or []).strip()
        meta = cand.get("groundingMetadata") or {}
        chunks = meta.get("groundingChunks") or []
        used = set()
        for sup in meta.get("groundingSupports") or []:
            used.update(sup.get("groundingChunkIndices") or [])
        cites = []
        for i, ch in enumerate(chunks):
            web = ch.get("web") or {}
            if web.get("uri"):
                cites.append(Citation(web["uri"], web.get("title", ""), "", i in used))
        r.citations = dedupe(cites)
        return r


class PerplexityEngine(Engine):
    name = "perplexity"
    default_model = os.environ.get("PERPLEXITY_MODEL", "sonar")

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("PERPLEXITY_API_KEY"))

    def ask(self, question: str) -> EngineResult:
        r = EngineResult(self.name, self.model)
        try:
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            r.error = f"perplexity: {e}"
            return r
        r.answer = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        cites = []
        results = data.get("search_results") or []
        urls = data.get("citations") or [s.get("url") for s in results]
        titles = {s.get("url"): s.get("title", "") for s in results}
        for i, url in enumerate(urls, 1):
            if url:
                # Perplexity 는 본문에 [1] 형태로 각주를 단다
                cites.append(Citation(url, titles.get(url, ""), "", f"[{i}]" in r.answer))
        r.citations = dedupe(cites)
        return r


def gemini_complete_text(prompt: str, system: str, model: str | None = None) -> str:
    """인사이트 해설용 단순 호출 (검색 없음)."""
    resp = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model or GeminiEngine.default_model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        },
    )
    cand = (resp.json().get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) or []).strip()
