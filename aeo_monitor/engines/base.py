"""AI 엔진 공통 인터페이스."""
from __future__ import annotations

from dataclasses import dataclass, field

# 소비자가 챗봇에 묻는 상황을 그대로 재현하기 위해 답변을 유도하지 않는 최소한의 지시만 둔다.
SYSTEM_PROMPT = (
    "당신은 한국 사용자를 돕는 AI 어시스턴트입니다. 질문에 한국어로 답하세요. "
    "최신 정보가 필요하면 웹 검색을 활용하세요."
)


@dataclass
class Citation:
    url: str
    title: str = ""
    cited_text: str = ""
    cited_in_answer: bool = False  # 답변 본문에서 실제로 인용(각주)됐는지, 검색만 됐는지


@dataclass
class EngineResult:
    engine: str
    model: str
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    error: str = ""


class Engine:
    name = "base"

    def __init__(self, model: str | None = None):
        self.model = model or self.default_model

    default_model = ""

    @classmethod
    def available(cls) -> bool:
        return True

    def ask(self, question: str) -> EngineResult:  # pragma: no cover - interface
        raise NotImplementedError


def dedupe(citations: list[Citation]) -> list[Citation]:
    seen: dict[str, Citation] = {}
    for c in citations:
        if not c.url:
            continue
        if c.url in seen:
            prev = seen[c.url]
            prev.cited_in_answer = prev.cited_in_answer or c.cited_in_answer
            prev.title = prev.title or c.title
            if c.cited_text and c.cited_text not in prev.cited_text:
                prev.cited_text = (prev.cited_text + " " + c.cited_text).strip()
        else:
            seen[c.url] = c
    return list(seen.values())
