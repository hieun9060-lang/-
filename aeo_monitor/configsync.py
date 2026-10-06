"""config/*.yaml 을 DB 로 반영한다 (정적 사이트 방식: 파일이 곧 설정, 매 실행마다 동기화)."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

import yaml

from . import config
from .content.collectors import detect_type
from .repo import Repo
from .seed import DEFAULT_GOAL, DEFAULT_SCHEDULE


class ConfigError(Exception):
    pass


def _load(name: str, required: bool = True) -> dict:
    path = config.CONFIG_DIR / name
    if not path.exists():
        if required:
            raise ConfigError(f"{name} 파일을 찾을 수 없습니다.")
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (줄 {mark.line + 1})" if mark else ""
        raise ConfigError(f"{name} 파일 형식이 잘못되었습니다{where}. 들여쓰기(스페이스)와 ':' 뒤 공백을 확인하세요.") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{name} 파일은 '이름: 값' 형식이어야 합니다.")
    return data


def stable_id(name: str) -> str:
    return "c_" + hashlib.sha1(name.strip().encode()).hexdigest()[:8]


def _urls(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        u = (x.get("url") if isinstance(x, dict) else x)
        if isinstance(u, str) and u.strip():
            out.append(u.strip())
    return out


def sync_config(repo: Repo) -> dict:
    brands_raw = _load("brands.yaml")
    mon = _load("monitor.yaml", required=False)
    settings = _load("settings.yaml")
    warnings: list[str] = []

    # ---- 회사 ----
    desired: list[dict] = []
    for b in brands_raw.get("brands", []):
        desired.append({"id": b["id"], "name": b["name"], "role": "ours" if b["id"] == brands_raw.get("target") else "competitor",
                        "grp": b.get("group", ""), "template_name": b.get("template_name", ""), "aliases": b.get("aliases", []),
                        "domains": b.get("domains", []), "near": b.get("near", []), "near_window": b.get("near_window", 12),
                        "near_exclude": b.get("near_exclude", []), "channels": _urls(b.get("channels"))})
    for c in mon.get("companies") or []:
        if not isinstance(c, dict) or not c.get("name"):
            warnings.append("companies 항목에는 name 이 필요합니다. 건너뜁니다.")
            continue
        name = str(c["name"]).strip()
        desired.append({"id": c.get("id") or stable_id(name), "name": name, "role": "competitor", "grp": "",
                        "template_name": name, "aliases": c.get("aliases") or [name], "domains": c.get("domains") or [],
                        "near": [], "near_window": 12, "near_exclude": [], "channels": _urls(c.get("channels"))})
    ids = [d["id"] for d in desired]
    if len(ids) != len(set(ids)):
        raise ConfigError("회사 id 가 중복되었습니다. brands.yaml / monitor.yaml 의 id·name 을 확인하세요.")
    if not any(d["role"] == "ours" for d in desired):
        raise ConfigError("brands.yaml 의 target 에 우리 학원 id 를 지정해야 합니다.")

    existing = {c["id"]: c for c in repo.companies(active_only=False)}
    for i, d in enumerate(desired):
        fields = {k: d[k] for k in ("name", "role", "grp", "template_name", "aliases", "domains", "near", "near_window", "near_exclude")}
        if d["id"] in existing:
            repo.update_company(d["id"], {**fields, "active": True, "sort": i})
        else:
            repo.create_company({"id": d["id"], **fields, "sort": i,
                                 "color_idx": 0 if d["role"] == "ours" else (len(existing) + i) % 7 + 1})
    for cid, c in existing.items():
        if cid not in ids and c["active"]:
            repo.update_company(cid, {"active": False})

    # ---- 채널 ----
    wanted: dict[str, list[str]] = {d["id"]: list(d["channels"]) for d in desired}
    for cid, urls in (mon.get("channels") or {}).items():
        if cid not in wanted:
            warnings.append(f"channels 의 '{cid}' 는 등록된 회사 id 가 아닙니다. 건너뜁니다.")
            continue
        wanted[cid] += _urls(urls)
    n_channels = 0
    for cid, urls in wanted.items():
        clean = []
        for u in dict.fromkeys(urls):
            p = urlparse(u if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u) else "https://" + u)
            if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
                warnings.append(f"올바르지 않은 주소를 건너뜁니다: {u}")
                continue
            clean.append(p.geturl())
        have = {c["url"]: c for c in repo.channels(cid)}
        for url, ch in have.items():
            if url not in clean:
                repo.delete_channel(ch["id"])
        for url in clean:
            if url not in have:
                repo.add_channel(cid, detect_type(url), url)
        n_channels += len(clean)

    # ---- 설정 ----
    repo.kv_set("workspace", {**{"name": "WORKSPACE-A", "title": "기숙학원 모니터링"}, **(mon.get("workspace") or {})})
    repo.kv_set("goal", {**DEFAULT_GOAL, **(mon.get("goal") or {})})
    repo.kv_set("schedule", {**DEFAULT_SCHEDULE, **(mon.get("schedule") or {})})
    repo.kv_set("target_group", brands_raw.get("target_group", {}))
    repo.kv_set("aeo", {k: settings[k] for k in ("engines", "models", "daily_questions", "window_days", "samples_per_question",
                                                  "concurrency", "include_templates", "trend_days", "ai_insight", "insight_engine") if k in settings})

    # ---- 질문 ----
    panel = set(settings.get("panel_questions", []))
    disabled = {str(x) for x in (mon.get("disable_questions") or [])}
    qs = [{"id": q["id"], "text": q["text"], "categories": q.get("categories", []), "origin": q.get("origin", "community_title"),
           "views": q.get("views", 0) or 0, "source_url": q.get("source_url", ""),
           "enabled": q.get("enabled", True) and q["id"] not in disabled, "panel": q["id"] in panel}
          for q in _load("questions.yaml", required=False).get("questions", [])]
    for j, text in enumerate(mon.get("extra_questions") or []):
        if isinstance(text, str) and len(text.strip()) >= 2:
            qs.append({"id": "x" + hashlib.sha1(text.strip().encode()).hexdigest()[:6], "text": text.strip(), "categories": ["추가"],
                       "origin": "custom", "enabled": True, "panel": False})
    keep = {q["id"] for q in qs}
    for old in repo.questions():
        if old["id"] not in keep:
            repo.delete_question(old["id"])
    for i, q in enumerate(qs):
        repo.upsert_question({**q, "sort": i})
    untracked = [d["name"] for d in desired if d["role"] == "competitor" and not wanted[d["id"]]]
    repo.kv_set("config_warnings", warnings)
    return {"companies": len(desired), "channels": n_channels, "warnings": warnings, "without_channels": len(untracked)}
