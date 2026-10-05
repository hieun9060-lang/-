"""Claude (Anthropic API + 서버측 web_search 도구)."""
from __future__ import annotations

import os

import anthropic

from .base import SYSTEM_PROMPT, Citation, Engine, EngineResult, dedupe


# 동적 필터링 웹검색(web_search_20260209)·effort·fallbacks 를 지원하지 않는 저가/구형 모델
_BASIC_MODELS = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5", "claude-opus-4-1")


def _is_basic(model: str) -> bool:
    return model.startswith(_BASIC_MODELS)


def _extra_params(model: str) -> dict:
    if _is_basic(model):
        return {}
    return {"output_config": {"effort": "medium"}, "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


def _quota_error(e: anthropic.APIStatusError) -> str:
    msg = str(e.message)
    if e.status_code == 402 or "credit balance" in msg.lower() or "billing" in msg.lower():
        return f"quota: 크레딧 소진 ({msg[:120]})"
    return f"api_error {e.status_code}: {msg}"


class ClaudeEngine(Engine):
    name = "claude"
    default_model = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def __init__(self, model: str | None = None):
        super().__init__(model)
        self.client = anthropic.Anthropic()

    def ask(self, question: str) -> EngineResult:
        result = EngineResult(self.name, self.model)
        messages: list = [{"role": "user", "content": question}]
        tools = [{
            "type": "web_search_20250305" if _is_basic(self.model) else "web_search_20260209",
            "name": "web_search",
            "max_uses": 5,
            "user_location": {"type": "approximate", "country": "KR", "timezone": "Asia/Seoul"},
        }]
        texts: list[str] = []
        cites: list[Citation] = []
        assistant_content: list = []
        try:
            # 서버 도구가 길어지면 pause_turn 으로 끊겨 오므로 이어서 요청
            for _ in range(5):
                resp = self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=tools,
                    **_extra_params(self.model),
                )
                result.model = resp.model
                for block in resp.content:
                    if block.type == "text":
                        texts.append(block.text)
                        for c in getattr(block, "citations", None) or []:
                            url = getattr(c, "url", None)
                            if url:
                                cites.append(Citation(url, getattr(c, "title", "") or "",
                                                      getattr(c, "cited_text", "") or "", True))
                    elif block.type == "web_search_tool_result":
                        content = getattr(block, "content", None)
                        if isinstance(content, list):  # 오류면 list 가 아닌 객체
                            for r in content:
                                url = getattr(r, "url", None)
                                if url:
                                    cites.append(Citation(url, getattr(r, "title", "") or ""))
                if resp.stop_reason == "pause_turn":
                    assistant_content.extend(resp.content)
                    messages = [messages[0], {"role": "assistant", "content": assistant_content}]
                    continue
                if resp.stop_reason == "refusal":
                    result.error = "refusal"
                break
        except anthropic.RateLimitError as e:
            result.error = f"rate_limit: {e}"
        except anthropic.APIStatusError as e:
            result.error = _quota_error(e)
        except anthropic.APIConnectionError as e:
            result.error = f"connection_error: {e}"
        result.answer = "".join(texts).strip()
        result.citations = dedupe(cites)
        return result


def complete_text(prompt: str, system: str, model: str | None = None, max_tokens: int = 16000) -> str:
    """인사이트 요약용 단순 호출 (웹검색 없음)."""
    client = anthropic.Anthropic()
    model = model or ClaudeEngine.default_model
    resp = client.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        **_extra_params(model),
    )
    if resp.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in resp.content if b.type == "text").strip()
