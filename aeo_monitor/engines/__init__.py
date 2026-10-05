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
    """names 가 없으면 API 키가 있는 실제 엔진을 모두 사용."""
    models = models or {}
    if not names:
        names = [n for n, cls in REGISTRY.items() if n != "mock" and cls.available()]
    engines = []
    for n in names:
        cls = REGISTRY[n]
        if n != "mock" and not cls.available():
            raise SystemExit(f"[{n}] API 키가 설정되지 않았습니다.")
        engines.append(cls(models.get(n)))
    return engines
