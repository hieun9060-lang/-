"""무료 한도용 질문 선택: 매일 고정 질문(panel) + 나머지는 날짜별 순환."""
from __future__ import annotations

import math
from datetime import date

from .config import Question


def split_panel(questions: list[Question], panel_ids: list[str]) -> tuple[list[Question], list[Question]]:
    ids = set(panel_ids or [])
    panel = [q for q in questions if q.id in ids]
    pool = sorted((q for q in questions if q.id not in ids), key=lambda q: q.id)
    return panel, pool


def rotation_per_day(daily: int, panel: list[Question]) -> int:
    return max(0, daily - len(panel))


def cycle_days(settings: dict, questions: list[Question]) -> int:
    panel, pool = split_panel(questions, settings.get("panel_questions", []))
    per_day = rotation_per_day(settings.get("daily_questions") or len(questions), panel)
    return max(1, math.ceil(len(pool) / per_day)) if per_day and pool else 1


def window_days(settings: dict, questions: list[Question]) -> int:
    w = settings.get("window_days", "auto")
    return cycle_days(settings, questions) if w in (None, "auto") else int(w)


def select_daily(questions: list[Question], settings: dict, run_date: str) -> list[Question]:
    """daily_questions 가 없거나 0이면 전체."""
    daily = settings.get("daily_questions") or 0
    if not daily or daily >= len(questions):
        for q in questions:
            q.panel = q.id in set(settings.get("panel_questions", []))
        return questions
    panel, pool = split_panel(questions, settings.get("panel_questions", []))
    for q in panel:
        q.panel = True
    k = rotation_per_day(daily, panel)
    if not k or not pool:
        return panel[:daily]
    day = date.fromisoformat(run_date).toordinal()
    start = (day * k) % len(pool)
    picked = [pool[(start + i) % len(pool)] for i in range(min(k, len(pool)))]
    for q in picked:
        q.panel = False
    return panel + picked
