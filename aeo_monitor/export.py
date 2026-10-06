"""그날의 AI 언급 분석 결과를 화면이 읽는 JSON 구조로 만든다."""
from __future__ import annotations

import json
from datetime import datetime

from .collect import KST
from .report import ENGINE_LABEL, group_mix


def build_payload(a: dict, briefing_rule: list[str], briefing_ai: str, ai_by: str, report_files: dict) -> dict:
    src = a["sources"]
    mixes = [("전체 출처", src["mix_all"]), ("답변 각주로 인용", src["mix_cited"]),
             ("이천캠퍼스 언급된 답변", src["mix_when_mentioned"]), ("이천캠퍼스 미언급 답변", src["mix_when_not"])]
    if src.get("baseline"):
        mixes.append(("엑셀 기준선 9/29", src["baseline"]))
    questions = []
    for q in a["questions"]:
        questions.append({
            "q": q["question"], "cat": q["categories"], "branded": q["branded"],
            "engines": {
                eng: {
                    "m": r["mentioned"], "rank": r["rank"], "sent": r["sentiment"], "brandOnly": r["brand_only"],
                    "otherCampus": r["other_campus"], "err": (r["error"] or "")[:160], "comp": r["competitors"],
                    "reasons": r["reasons"], "snippet": r["snippet"][:240],
                    "src": [{"d": d, "t": t, "u": u, "target": tg} for d, t, u, tg in r["sources"]],
                } for eng, r in q["engines"].items()
            },
        })
    from .analyze import REASONS
    return {
        "generatedAt": datetime.now(KST).isoformat(timespec="minutes"),
        "date": a["run"]["run_date"], "demo": bool(a["run"]["demo"]),
        "engines": json.loads(a["run"]["engines"]), "engineLabels": ENGINE_LABEL,
        "target": a["target"], "kpi": a["kpi"], "delta": a["delta"], "trend": a["trend"],
        "briefing": briefing_rule, "ai": briefing_ai, "aiBy": ai_by,
        "byEngine": a["by_engine"], "byCategory": a["by_category"], "byBranded": a["by_branded"],
        "sov": a["sov"], "templateCompare": a["template_compare"],
        "sourceMix": [{"name": n, "groups": group_mix(m), "raw": m or {}} for n, m in mixes],
        "topDomains": src["top_domains"], "targetDomains": src["target_source_domains"],
        "competitorDomains": src["domains_when_competitor"],
        "reasonsMentioned": a["reasons_mentioned"], "reasonsNot": a["reasons_not"], "reasonLabels": REASONS,
        "actions": a["actions"], "questions": questions,
        "files": report_files,
    }
