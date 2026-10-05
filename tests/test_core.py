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
