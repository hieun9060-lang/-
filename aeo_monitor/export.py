"""인사이트 앱(docs/index.html)이 읽는 JSON 데이터 내보내기.

docs/data/index.json        : 측정일 목록 + 날짜별 요약(추이)
docs/data/days/<날짜>.json  : 그날의 전체 인사이트
docs/data/latest.json       : 가장 최근 날짜 (= days/<최신>.json)
데모 실행은 docs/data-demo/ 에 따로 저장되어 실제 데이터와 섞이지 않습니다 (앱 주소 뒤에 ?demo=1).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .collect import KST
from .report import ENGINE_LABEL, group_mix


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


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


def export_app_data(docs_dir: Path, a: dict, briefing_rule: list[str], briefing_ai: str, ai_by: str,
                    report_files: dict) -> Path:
    base = docs_dir / ("data-demo" if a["run"]["demo"] else "data")
    payload = build_payload(a, briefing_rule, briefing_ai, ai_by, report_files)
    day = a["run"]["run_date"]
    _dump(base / "days" / f"{day}.json", payload)

    idx_path = base / "index.json"
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        idx = {"days": []}
    k = a["kpi"]
    entry = {"date": day, "todayRate": k.get("today_rate"), "windowRate": k["target_rate"],
             "byEngine": {r["key"]: r["rate"] for r in a["by_engine"]}, "officialRate": k["official_cited_rate"],
             "brandOnlyRate": k["brand_only_rate"], "topAction": a["actions"][0]["title"] if a["actions"] else ""}
    days = [d for d in idx.get("days", []) if d["date"] != day] + [entry]
    days.sort(key=lambda d: d["date"])
    latest = days[-1]["date"]
    _dump(idx_path, {"target": a["target"], "latest": latest, "days": days})
    if latest == day:
        _dump(base / "latest.json", payload)
    return base
