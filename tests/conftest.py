import pytest


@pytest.fixture(autouse=True)
def _no_real_api_keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "PERPLEXITY_API_KEY",
              "SLACK_WEBHOOK_URL", "SMTP_HOST", "GITHUB_TOKEN"):
        monkeypatch.delenv(k, raising=False)
