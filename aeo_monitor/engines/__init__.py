from .base import Citation, Engine, EngineResult  # noqa: F401
from .claude import ClaudeEngine
from .mock import MockEngine
from .others import GeminiEngine, OpenAIEngine, PerplexityEngine

REGISTRY: dict[str, type[Engine]] = {
    "claude": ClaudeEngine,
    "chatgpt": OpenAIEngine,
    "gemini": GeminiEngine,
    "perplexity": PerplexityEngine,
    "mock": MockEngine,
}


def build_engines(names: list[str] | None, models: dict | None = None) -> list[Engine]:
    """names 가 없으면 API 키가 있는 실제 엔진을 모두 사용. 키가 없는 엔진은 경고 후 건너뜀."""
    import logging
    models = models or {}
    if not names:
        names = [n for n, cls in REGISTRY.items() if n != "mock" and cls.available()]
    engines = []
    for n in names:
        cls = REGISTRY[n]
        if n != "mock" and not cls.available():
            logging.getLogger(__name__).warning("[%s] API 키가 없어 건너뜁니다.", n)
            continue
        engines.append(cls(models.get(n)))
    return engines
