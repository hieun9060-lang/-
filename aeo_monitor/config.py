"""설정 파일(config/*.yaml) 로딩."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("AEO_CONFIG_DIR", ROOT / "config"))
DATA_DIR = Path(os.environ.get("AEO_DATA_DIR", ROOT / "data"))
DOCS_DIR = Path(os.environ.get("AEO_DOCS_DIR", ROOT / "docs"))


@dataclass
class Brand:
    id: str
    name: str
    aliases: list[str]
    template_name: str = ""
    group: str = ""
    near: list[list[str]] = field(default_factory=list)
    near_window: int = 12
    near_exclude: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


@dataclass
class BrandConfig:
    target_id: str
    brands: list[Brand]
    group_name: str
    group_aliases: list[str]
    other_campus_words: list[str]

    @property
    def target(self) -> Brand:
        return self.by_id(self.target_id)

    def by_id(self, brand_id: str) -> Brand:
        for b in self.brands:
            if b.id == brand_id:
                return b
        raise KeyError(brand_id)

    @property
    def competitors(self) -> list[Brand]:
        return [b for b in self.brands if b.id != self.target_id]


@dataclass
class Question:
    id: str
    text: str
    categories: list[str]
    origin: str  # community_title / representative / template
    branded: bool  # 질문에 이투스 브랜드명이 들어가 있는지
    brand_scope: str = ""  # 템플릿 질문이면 대상 학원 id
    template_id: str = ""
    views: int = 0
    source_url: str = ""
    enabled: bool = True
    panel: bool = False  # 매일 고정 질문 여부


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_brands() -> BrandConfig:
    raw = _load_yaml("brands.yaml")
    brands = [Brand(**b) for b in raw["brands"]]
    group = raw.get("target_group", {})
    return BrandConfig(
        target_id=raw["target"],
        brands=brands,
        group_name=group.get("name", ""),
        group_aliases=group.get("aliases", []),
        other_campus_words=group.get("other_campus_words", []),
    )


def load_source_rules() -> dict:
    return _load_yaml("sources.yaml")


def load_settings() -> dict:
    return _load_yaml("settings.yaml")


def is_branded(text: str, brands: BrandConfig | None = None) -> bool:
    """질문에 우리 학원(브랜드) 표기가 들어 있는지."""
    t = re.sub(r"\s+", "", text).lower()
    keys = ["이투스", "etoos"]
    if brands and brands.target_id:
        tgt = brands.target
        keys = list(tgt.aliases) + [tgt.name] + list(brands.group_aliases)
        m = re.match(r"^[가-힣A-Za-z]+", tgt.name)
        if m:
            keys.append(m.group(0))
    return any(k and re.sub(r"\s+", "", k).lower() in t for k in keys)


def _is_branded(text: str) -> bool:  # 이전 이름 호환
    return is_branded(text)


def template_questions(brands: BrandConfig) -> list[Question]:
    """question_templates.yaml 의 템플릿 × 대상 학원."""
    out: list[Question] = []
    tpl_path = CONFIG_DIR / "question_templates.yaml"
    if not tpl_path.exists():
        return out
    tpl = _load_yaml("question_templates.yaml")
    scope = tpl.get("brands", "all")
    known = {b.id: b for b in brands.brands}
    scoped = brands.brands if scope == "all" else [known[i] for i in scope if i in known]
    for t in tpl.get("templates", []):
        if not t.get("enabled", True):
            continue
        for b in scoped:
            out.append(Question(id=f"tpl_{t['id']}__{b.id}", text=t["text"].format(brand=b.template_name or b.name),
                                categories=t.get("categories", []), origin="template", branded=True,
                                brand_scope=b.id, template_id=t["id"]))
    return out


def load_questions(brands: BrandConfig | None = None) -> list[Question]:
    """questions.yaml(엑셀에서 추출한 실제 질문) + question_templates.yaml(학원별 동일 질문)."""
    brands = brands or load_brands()
    out: list[Question] = []
    raw = _load_yaml("questions.yaml")
    for q in raw.get("questions", []):
        if not q.get("enabled", True):
            continue
        out.append(Question(id=q["id"], text=q["text"], categories=q.get("categories", []),
                            origin=q.get("origin", "community_title"), branded=is_branded(q["text"], brands),
                            views=q.get("views", 0) or 0, source_url=q.get("source_url", "")))
    return out + template_questions(brands)
