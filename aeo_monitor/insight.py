"""오늘의 핵심 인사이트 문장 생성 (규칙 기반 + 선택적으로 Claude 해설)."""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

SYSTEM = (
    "당신은 AEO/GEO(생성형 AI 검색 최적화) 컨설턴트입니다. 기숙학원 마케팅 담당자가 매일 아침 9시에 읽을 "
    "브리핑을 씁니다. 주어진 JSON 수치만 근거로 쓰고, 수치에 없는 사실은 만들지 마세요. "
    "한국어로, 마크다운 글머리표 5~8개 이내로: (1) 오늘 이천캠퍼스가 언급된/안 된 핵심 이유, "
    "(2) 전일 대비 변화, (3) 경쟁 학원 대비 위치, (4) 출처 측면의 원인, (5) 오늘 바로 할 일 2~3개."
)


def rule_based(a: dict) -> list[str]:
    k = a["kpi"]
    out = []
    if "today_rate" in k:
        out.append(f"오늘 {k['today_basis']} 답변 {k['today_n']}건 중 **{a['target']}** 언급 {k['today_hit']}건 "
                   f"(**{k['today_rate']}%**).")
    if a.get("delta"):
        d = a["delta"]
        arrow = "▲" if d["diff"] > 0 else ("▼" if d["diff"] < 0 else "–")
        out.append(f"전 측정일({d['date']}) {d['rate']}% 대비 {arrow} {abs(d['diff'])}%p.")
    out.append(f"최근 {k.get('window_days', 1)}일 누적: 질문 {k.get('questions_covered', 0)}개 · 답변 {k['core_responses']}건 중 "
               f"{k['target_mentions']}건 언급 (**{k['target_rate']}%**).")
    if k["brand_only"]:
        out.append(f"'이투스247'만 언급되고 이천캠퍼스는 빠진 답변 {k['brand_only']}건 — 캠퍼스 혼동/엔티티 불명확.")
    leader = next((s for s in a["sov"] if s["mentions"]), None)
    tgt = next((s for s in a["sov"] if s["is_target"]), None)
    if leader and tgt and not leader["is_target"]:
        out.append(f"가장 많이 언급된 학원은 {leader['name']}({leader['rate']}%), 이천캠퍼스는 {tgt['rate']}%.")
    elif leader and leader["is_target"]:
        out.append(f"이천캠퍼스가 동일 질문 세트에서 가장 많이 언급됨({leader['rate']}%).")
    out.append(f"공식 홈페이지(이천캠퍼스) 출처 인용률 {k['official_cited_rate']}%.")
    if a["reasons_not"]:
        r = a["reasons_not"][0]
        out.append(f"미언급 주원인: {r[0]} ({r[1]}건).")
    if a["actions"]:
        out.append(f"최우선 과제: **{a['actions'][0]['title']}**.")
    return out


def compact_for_llm(a: dict) -> dict:
    return {
        "target": a["target"], "date": a["run"]["run_date"], "kpi": a["kpi"], "delta": a["delta"],
        "trend": a["trend"][-7:], "by_engine": a["by_engine"], "by_category": a["by_category"],
        "by_branded": a["by_branded"],
        "share_of_voice_top": [{k: s[k] for k in ("name", "rate", "first", "avg_rank")} for s in a["sov"][:8]],
        "same_question_compare": [{k: t[k] for k in ("name", "self_rate", "official_rate", "avg_cites")} for t in a["template_compare"]],
        "source_mix_all": a["sources"]["mix_all"], "source_mix_when_mentioned": a["sources"]["mix_when_mentioned"],
        "source_mix_when_not": a["sources"]["mix_when_not"],
        "domains_citing_target": a["sources"]["target_source_domains"][:8],
        "domains_when_competitor_wins": a["sources"]["domains_when_competitor"][:8],
        "reasons_mentioned": a["reasons_mentioned"], "reasons_not_mentioned": a["reasons_not"],
        "top_actions": [{k: x[k] for k in ("title", "reason", "count", "examples")} for x in a["actions"][:5]],
        "unmentioned_examples": [q["question"] for q in a["questions"] if not any(e["mentioned"] for e in q["engines"].values())][:10],
    }


def ai_briefing(a: dict, models: dict | None = None, prefer: str = "gemini") -> tuple[str, str]:
    """(해설, 작성 엔진명). 기본은 무료인 Gemini, 없으면 Claude. 실패해도 리포트는 규칙 기반으로 생성."""
    from .engines.claude import ClaudeEngine, complete_text
    from .engines.others import GeminiEngine, gemini_complete_text
    models = models or {}
    prompt = f"오늘 측정 결과(JSON):\n{json.dumps(compact_for_llm(a), ensure_ascii=False)}"
    writers = {
        "gemini": (GeminiEngine, lambda: gemini_complete_text(prompt, SYSTEM, models.get("gemini")), "Gemini"),
        "claude": (ClaudeEngine, lambda: complete_text(prompt, SYSTEM, models.get("claude")), "Claude"),
    }
    order = [prefer] + [k for k in writers if k != prefer]
    for key in order:
        cls, fn, label = writers.get(key, (None, None, None))
        if not cls or not cls.available():
            continue
        try:
            text = fn()
            if text:
                return text, label
        except Exception as e:  # noqa: BLE001
            log.warning("AI 해설(%s) 생성 실패: %s", label, e)
    return "", ""
