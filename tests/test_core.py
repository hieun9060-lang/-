import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeo_monitor import config
from aeo_monitor.detect import detect_group_only, detect_mentions
from aeo_monitor.sources import OFFICIAL, SourceClassifier

BR = config.load_brands()
CL = SourceClassifier(config.load_source_rules(), BR)
T = BR.target_id


@pytest.mark.parametrize("text", [
    "이투스247 이천기숙학원은 관리가 체계적입니다.",
    "이천 이투스 247 기숙학원을 추천합니다",
    "이천에 있는 이투스 기숙학원은",
    "이투스이천 후기",
])
def test_target_detected(text):
    assert detect_mentions(text, BR)[T].mentioned


@pytest.mark.parametrize("text", [
    "이투스247 안성기숙학원과 이천청솔을 비교하면",   # '이천청솔'의 이천은 이투스 이천이 아님
    "강남대성 퀘타와 러셀 기숙학원",
    "이투스247 송파 재수정규반 모집",
])
def test_target_not_detected(text):
    assert not detect_mentions(text, BR)[T].mentioned


def test_rank_and_competitors():
    m = detect_mentions("1. 강남대성 퀘타 2. 메가스터디 기숙학원 3. 이투스247 이천", BR)
    assert m["quetta"].rank == 1 and m["russel"].rank == 2 and m[T].rank == 3


def test_brand_only_campus_confusion():
    text = "이투스247 송파 캠퍼스는 재수정규반을 운영합니다."
    m = detect_mentions(text, BR)
    g = detect_group_only(text, BR, m)
    assert g["brand_only"] and "송파" in g["other_campus"]


def test_sentiment_negative():
    m = detect_mentions("이투스247 이천은 급식이 아쉽다는 불만이 많습니다", BR)
    assert m[T].sentiment == "negative"


@pytest.mark.parametrize("url,expected", [
    ("https://www.dhnews.co.kr/news/articleView.html?idxno=1", "언론/보도자료"),
    ("https://academy.prompie.com/a/1", "제3자 학원정보 플랫폼"),
    ("https://apps.apple.com/kr/app/etoos247/id1", "자사(앱)"),
    ("https://apps.apple.com/kr/app/other/id1", "기타/무관"),
    ("https://cafe.naver.com/suhui/1", "커뮤니티(수만휘·오르비 등)"),
    ("https://orbi.kr/0001", "커뮤니티(수만휘·오르비 등)"),
    ("https://blog.naver.com/abc/1", "네이버 블로그"),
    ("https://www.megastudy.net/russel", "경쟁사 공식자료"),
    ("https://etoos247icheon.co.kr/faq", OFFICIAL),
])
def test_source_classification(url, expected):
    assert CL.classify(url) == expected


def test_gemini_redirect_resolves_title():
    url, dom = CL.resolve("https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz", "orbi.kr")
    assert dom == "orbi.kr" and CL.classify(url) == "커뮤니티(수만휘·오르비 등)"


def test_questions_loaded_from_excel_and_templates():
    qs = config.load_questions(BR)
    assert sum(q.origin != "template" for q in qs) >= 60
    tpl = [q for q in qs if q.origin == "template"]
    assert tpl and all("{brand}" not in q.text for q in tpl)
    assert any(q.brand_scope == T for q in tpl)


def test_claude_engine_parsing(monkeypatch):
    """Anthropic 응답 블록 → 답변·출처 파싱 (네트워크 없이)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from aeo_monitor.engines.claude import ClaudeEngine
    eng = ClaudeEngine()
    blocks = [
        SimpleNamespace(type="server_tool_use"),
        SimpleNamespace(type="web_search_tool_result", content=[
            SimpleNamespace(url="https://orbi.kr/1", title="이투스247 이천 후기"),
            SimpleNamespace(url="https://dhnews.co.kr/2", title="기숙학원 소식")]),
        SimpleNamespace(type="text", text="이투스247 이천기숙학원은 ", citations=[
            SimpleNamespace(url="https://orbi.kr/1", title="이투스247 이천 후기", cited_text="관리가 엄격")]),
        SimpleNamespace(type="text", text="관리가 엄격합니다.", citations=None),
    ]
    resp = SimpleNamespace(content=blocks, stop_reason="end_turn", model="claude-opus-5-5")
    eng.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resp)))
    r = eng.ask("질문")
    assert r.answer == "이투스247 이천기숙학원은 관리가 엄격합니다."
    by_url = {c.url: c for c in r.citations}
    assert by_url["https://orbi.kr/1"].cited_in_answer and not by_url["https://dhnews.co.kr/2"].cited_in_answer


def test_end_to_end_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DOCS_DIR", tmp_path / "docs")
    from aeo_monitor.cli import main
    assert main(["run", "--engines", "mock", "--limit", "12", "--date", "2026-10-04"]) == 0
    assert main(["run", "--engines", "mock", "--limit", "12", "--date", "2026-10-05"]) == 0
    rep = tmp_path / "docs" / "reports"
    html = (rep / "demo-2026-10-05.html").read_text(encoding="utf-8")
    assert "DEMO" in html and "AEO/GEO 개선과제" in html and "경쟁 기숙학원" in html
    assert (rep / "demo-2026-10-05.xlsx").exists()
    # 데모는 공개 리포트(index.html)를 덮어쓰지 않는다
    assert not (tmp_path / "docs" / "index.html").exists()


def test_gemini_engine_parsing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    from aeo_monitor.engines import others

    payload = {"candidates": [{
        "content": {"parts": [{"text": "이투스247 이천기숙학원은 "}, {"text": "관리가 엄격합니다."}]},
        "groundingMetadata": {
            "groundingChunks": [
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a", "title": "orbi.kr"}},
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/b", "title": "dhnews.co.kr"}},
            ],
            "groundingSupports": [{"groundingChunkIndices": [0]}],
        },
    }]}

    class Resp:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(others.requests, "post", lambda *a, **kw: Resp())
    r = others.GeminiEngine().ask("질문")
    assert r.answer == "이투스247 이천기숙학원은 관리가 엄격합니다."
    assert [c.cited_in_answer for c in r.citations] == [True, False]
    url, dom = CL.resolve(r.citations[0].url, r.citations[0].title)
    assert dom == "orbi.kr" and CL.classify(url) == "커뮤니티(수만휘·오르비 등)"


def test_settings_three_engines_free_budget():
    st = config.load_settings()
    assert st["engines"] == ["gemini", "chatgpt", "claude"]
    assert st["daily_questions"] <= 10


def test_daily_selection_panel_and_rotation_covers_all():
    from datetime import date, timedelta
    from aeo_monitor.schedule import cycle_days, select_daily
    st = config.load_settings()
    qs = [q for q in config.load_questions(BR) if q.origin != "template"]
    days = cycle_days(st, qs)
    seen = set()
    d0 = date(2026, 10, 6)
    for i in range(days):
        picked = select_daily(config.load_questions(BR)[: len(qs)], st, (d0 + timedelta(days=i)).isoformat())
        assert len(picked) == st["daily_questions"]
        assert {q.id for q in picked if q.panel} == set(st["panel_questions"])
        seen |= {q.id for q in picked}
    assert seen == {q.id for q in qs}  # 한 주기 안에 모든 질문을 한 번 이상 측정


def test_quota_stops_engine_for_the_day(tmp_path):
    from aeo_monitor.collect import run_collection
    from aeo_monitor.engines import EngineResult, MockEngine
    from aeo_monitor.storage import Store

    class Broke(MockEngine):
        name = "claude"
        calls = 0

        def ask(self, q):
            Broke.calls += 1
            return EngineResult("claude", "x", error="quota: 크레딧 소진")

    qs = [q for q in config.load_questions(BR) if q.origin != "template"][:6]
    store = Store(tmp_path / "t.db")
    run_collection(store, [Broke()], qs, BR, CL, concurrency=1, run_date="2026-10-06")
    assert Broke.calls == 1
    errs = [r["error"] for r in store.responses(1)]
    assert sum(e.startswith("skipped") for e in errs) == 5


def test_gemini_daily_quota_not_retried(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    from aeo_monitor.engines import others
    calls = []

    class R:
        status_code = 429
        headers: dict = {}
        text = '{"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}'

    monkeypatch.setattr(others.requests, "post", lambda *a, **k: calls.append(1) or R())
    r = others.GeminiEngine().ask("q")
    assert r.error.startswith("quota:") and len(calls) == 1


def test_claude_haiku_uses_basic_web_search(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from aeo_monitor.engines.claude import ClaudeEngine
    eng = ClaudeEngine("claude-haiku-4-5")
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="답", citations=None)],
                               stop_reason="end_turn", model="claude-haiku-4-5")

    eng.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert eng.ask("q").answer == "답"
    assert seen["tools"][0]["type"] == "web_search_20250305"
    assert "output_config" not in seen and "fallbacks" not in seen
