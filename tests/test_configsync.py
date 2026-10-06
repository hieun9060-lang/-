import shutil

import pytest

from aeo_monitor import config
from aeo_monitor.configsync import ConfigError, sync_config
from aeo_monitor.repo import Repo
from aeo_monitor.storage import Store


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    d = tmp_path / "config"
    shutil.copytree(config.CONFIG_DIR, d)
    monkeypatch.setattr(config, "CONFIG_DIR", d)
    return d


def repo_of(tmp_path):
    return Repo(Store(tmp_path / "t.db"))


def test_first_sync_from_defaults(cfg, tmp_path):
    repo = repo_of(tmp_path)
    r = sync_config(repo)
    assert r["companies"] == 14 and r["channels"] == 0 and r["warnings"] == []
    assert repo.our_company()["id"] == "etoos247_icheon" and len(repo.questions()) == 63
    assert [q["id"] for q in repo.questions() if q["panel"]] == ["q001", "q002", "q017", "q019"]
    assert repo.kv_get("goal")["title"] == "자사와 경쟁사 흐름 비교"


def test_channels_companies_questions_follow_the_file(cfg, tmp_path):
    repo = repo_of(tmp_path)
    sync_config(repo)
    (cfg / "monitor.yaml").write_text("""
goal: {title: 새 기준, desc: 설명}
channels:
  etoos247_icheon:
    - https://blog.naver.com/abc
    - www.youtube.com/@icheon
    - ftp://bad.example.com
  없는회사: [https://x.com]
companies:
  - name: 새로운 학원
    channels: [https://newacademy.kr]
extra_questions: ["새 질문입니다 어때요"]
disable_questions: [q010]
""", encoding="utf-8")
    r = sync_config(repo)
    assert r["channels"] == 3 and len(r["warnings"]) == 2
    ch = {c["url"]: c["type"] for c in repo.channels("etoos247_icheon")}
    assert ch == {"https://blog.naver.com/abc": "blog", "https://www.youtube.com/@icheon": "youtube"}
    new = next(c for c in repo.companies() if c["name"] == "새로운 학원")
    assert repo.channels(new["id"])[0]["type"] == "homepage"
    assert repo.kv_get("goal")["title"] == "새 기준"
    qs = {q["id"]: q for q in repo.questions()}
    assert qs["q010"]["enabled"] is False and any(q["text"] == "새 질문입니다 어때요" for q in qs.values())
    # 채널 하나를 지우면 DB 에서도 빠지고, 이미 수집한 게시물은 남는다
    repo.upsert_post(company_id="etoos247_icheon", channel_id=repo.channels("etoos247_icheon")[0]["id"], platform="blog",
                     url="https://x/1", title="t", snippet="", body="", topic="기타", published_at=None, post_date="2026-10-01")
    (cfg / "monitor.yaml").write_text("channels: {}\n", encoding="utf-8")
    sync_config(repo)
    assert repo.channels("etoos247_icheon") == [] and len(repo.posts("2026-10-01", "2026-10-01")) == 1
    assert all(c["name"] != "새로운 학원" for c in repo.companies())  # 파일에서 빠진 회사는 숨김


def test_stable_ids_and_idempotent(cfg, tmp_path):
    (cfg / "monitor.yaml").write_text("companies:\n  - name: 새로운 학원\n", encoding="utf-8")
    repo = repo_of(tmp_path)
    sync_config(repo); first = {c["name"]: c["id"] for c in repo.companies()}
    sync_config(repo)
    assert {c["name"]: c["id"] for c in repo.companies()} == first and len(repo.questions()) == 63


def test_friendly_errors(cfg, tmp_path):
    (cfg / "monitor.yaml").write_text("channels:\n  etoos247_icheon: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="monitor.yaml"):
        sync_config(repo_of(tmp_path))
    (cfg / "monitor.yaml").write_text("channels: {}\n", encoding="utf-8")
    (cfg / "brands.yaml").write_text("target: nobody\nbrands:\n  - {id: a, name: A, aliases: [A]}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="target"):
        sync_config(repo_of(tmp_path))
