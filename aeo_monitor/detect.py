"""AI 답변 텍스트에서 학원 언급을 찾아내는 로직."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Brand, BrandConfig

_STRIP = re.compile(r"[\s\-_·•\.\,\(\)\[\]\"'“”‘’/]+")

POSITIVE = ["추천", "장점", "좋", "우수", "체계", "만족", "꼼꼼", "관리가 잘", "효과", "인기", "강점", "높은 합격", "깔끔", "쾌적"]
NEGATIVE = ["단점", "최악", "비추", "불만", "아쉽", "별로", "부족", "논란", "후회", "힘들", "문제", "열악", "가지마", "낡"]


def normalize(text: str) -> tuple[str, list[int]]:
    """공백·구두점 제거 + 소문자. 정규화 문자열과 원문 인덱스 매핑을 반환."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if _STRIP.fullmatch(ch):
            continue
        chars.append(ch.lower())
        index.append(i)
    return "".join(chars), index


def _norm(s: str) -> str:
    return normalize(s)[0]


@dataclass
class Mention:
    brand_id: str
    mentioned: bool
    first_pos: int = -1  # 원문 기준 첫 언급 위치
    count: int = 0
    rank: int = 0  # 답변 내 등장 순서(1 = 가장 먼저 언급)
    sentiment: str = ""  # positive / negative / mixed / neutral
    snippet: str = ""


def _find_positions(norm_text: str, brand: Brand) -> list[int]:
    positions: set[int] = set()
    for alias in brand.aliases:
        a = _norm(alias)
        if not a:
            continue
        start = 0
        while (p := norm_text.find(a, start)) != -1:
            positions.add(p)
            start = p + 1

    if brand.near:
        excluded: list[tuple[int, int]] = []
        for ex in brand.near_exclude:
            e = _norm(ex)
            start = 0
            while (p := norm_text.find(e, start)) != -1:
                excluded.append((p, p + len(e)))
                start = p + 1

        def all_pos(tok: str) -> list[int]:
            t = _norm(tok)
            res, start = [], 0
            while (p := norm_text.find(t, start)) != -1:
                if not any(s <= p < e for s, e in excluded):
                    res.append(p)
                start = p + 1
            return res

        for a, b in brand.near:
            pa, pb = all_pos(a), all_pos(b)
            for x in pa:
                for y in pb:
                    if abs(x - y) <= brand.near_window:
                        positions.add(min(x, y))
    return sorted(positions)


def _sentiment(text: str, pos: int, window: int = 80) -> str:
    seg = text[max(0, pos - window // 2): pos + window]
    p = sum(seg.count(w) for w in POSITIVE)
    n = sum(seg.count(w) for w in NEGATIVE)
    if p and n:
        return "mixed"
    if p:
        return "positive"
    if n:
        return "negative"
    return "neutral"


def detect_mentions(text: str, cfg: BrandConfig) -> dict[str, Mention]:
    """모든 학원의 언급 여부/순위/감성 판단."""
    norm_text, index = normalize(text or "")
    result: dict[str, Mention] = {}
    for brand in cfg.brands:
        pos = _find_positions(norm_text, brand)
        if not pos:
            result[brand.id] = Mention(brand.id, False)
            continue
        orig = index[pos[0]] if pos[0] < len(index) else 0
        sentiments = {_sentiment(text, index[p]) for p in pos if p < len(index)}
        if "positive" in sentiments and "negative" in sentiments or "mixed" in sentiments:
            s = "mixed"
        elif "negative" in sentiments:
            s = "negative"
        elif "positive" in sentiments:
            s = "positive"
        else:
            s = "neutral"
        snippet = text[max(0, orig - 40): orig + 100].replace("\n", " ").strip()
        result[brand.id] = Mention(brand.id, True, orig, len(pos), 0, s, snippet)

    ordered = sorted((m for m in result.values() if m.mentioned), key=lambda m: m.first_pos)
    for i, m in enumerate(ordered, 1):
        m.rank = i
    return result


def detect_group_only(text: str, cfg: BrandConfig, mentions: dict[str, Mention]) -> dict:
    """대상 캠퍼스는 없지만 '이투스247' 브랜드만 나온 경우, 타 캠퍼스 혼동 여부."""
    norm_text, _ = normalize(text or "")
    group_hit = any(_norm(a) in norm_text for a in cfg.group_aliases)
    target_hit = mentions.get(cfg.target_id, Mention(cfg.target_id, False)).mentioned
    other_campus = []
    if group_hit:
        for w in cfg.other_campus_words:
            # "이투스 + 타 캠퍼스 지역명"이 가까이 붙어 나올 때만
            wn = _norm(w)
            for alias in cfg.group_aliases + ["이투스"]:
                an = _norm(alias)
                start = 0
                while (p := norm_text.find(an, start)) != -1:
                    near = norm_text[max(0, p - 10): p + len(an) + 10]
                    if wn in near:
                        other_campus.append(w)
                        break
                    start = p + 1
    return {
        "group_mentioned": group_hit or target_hit,
        "brand_only": group_hit and not target_hit,
        "other_campus": sorted(set(other_campus)),
    }


def text_mentions_brand(text: str, brand: Brand) -> bool:
    norm_text, _ = normalize(text or "")
    return bool(_find_positions(norm_text, brand))
