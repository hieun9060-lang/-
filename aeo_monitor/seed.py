"""첫 실행 시 config/*.yaml 의 기본값을 DB로 옮긴다 (이후에는 앱에서 수정)."""
from __future__ import annotations

import os

from . import config
from .repo import Repo

DEFAULT_GOAL = {"title": "자사와 경쟁사 흐름 비교", "desc": "이 기준에 맞춰 경쟁사 변화와 업계 흐름을 구분합니다."}
DEFAULT_SCHEDULE = {"run_time": "07:00", "notify_time": "09:00", "auto_analysis": True}


def seed_defaults(repo: Repo) -> None:
    raw = config._load_yaml("brands.yaml")
    if not repo.companies(active_only=False):
        for i, b in enumerate(raw.get("brands", [])):
            repo.create_company({
                "id": b["id"], "name": b["name"], "role": "ours" if b["id"] == raw.get("target") else "competitor",
                "color_idx": 0 if b["id"] == raw.get("target") else (i % 7) + 1, "grp": b.get("group", ""),
                "template_name": b.get("template_name", ""), "aliases": b.get("aliases", []),
                "domains": b.get("domains", []), "near": b.get("near", []), "near_window": b.get("near_window", 12),
                "near_exclude": b.get("near_exclude", []), "sort": i,
                "track_ai": True,
            })
    if repo.kv_get("target_group") is None:
        repo.kv_set("target_group", raw.get("target_group", {}))

    st = config.load_settings()
    if repo.kv_get("aeo") is None:
        repo.kv_set("aeo", {k: st[k] for k in (
            "engines", "models", "daily_questions", "window_days", "samples_per_question", "concurrency",
            "include_templates", "trend_days", "ai_insight", "insight_engine") if k in st})

    if not repo.questions():
        panel = set(st.get("panel_questions", []))
        for i, q in enumerate(config._load_yaml("questions.yaml").get("questions", [])):
            repo.upsert_question({"id": q["id"], "text": q["text"], "categories": q.get("categories", []),
                                  "origin": q.get("origin", "community_title"), "views": q.get("views", 0) or 0,
                                  "source_url": q.get("source_url", ""), "enabled": q.get("enabled", True),
                                  "panel": q["id"] in panel, "sort": i})

    if repo.kv_get("goal") is None:
        repo.kv_set("goal", DEFAULT_GOAL)
    if repo.kv_get("schedule") is None:
        repo.kv_set("schedule", DEFAULT_SCHEDULE)
    if repo.kv_get("workspace") is None:
        repo.kv_set("workspace", {"name": os.environ.get("APP_WORKSPACE", "WORKSPACE-A"), "title": "기숙학원 모니터링"})
