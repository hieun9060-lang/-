"""업체 동향 요약, 주간/월간 분석, 챗봇, 리서치 기준 추천."""
from __future__ import annotations

import json
from collections import Counter

from .. import llm
from ..repo import Repo
from ..timeutil import now_kst, period_range, shift_period
from .stats import period_stats, previous_period

SYSTEM = ("당신은 기숙학원 마케팅 리서처입니다. 자사(우리 학원)와 경쟁 학원이 블로그·유튜브·홈페이지에 올린 "
          "게시물을 보고 흐름과 시사점을 한국어로 간결하게 정리합니다. " + llm.UNTRUSTED_NOTE)


def _goal(repo: Repo) -> str:
    g = repo.kv_get("goal", {})
    return f"{g.get('title', '')} — {g.get('desc', '')}".strip(" —")


def _ai_cfg(repo: Repo) -> tuple[str, dict]:
    a = repo.kv_get("aeo", {})
    return a.get("insight_engine", "gemini"), a.get("models", {})


def _post_brief(p: dict, n: int = 220) -> dict:
    return {"제목": p["title"], "주제": p["topic"], "채널": p["platform"], "내용": (p.get("body") or p.get("snippet") or "")[:n]}


# ---------- 일간 업체 동향 ----------
def rule_digest(company: dict, posts: list[dict]) -> dict:
    topics = Counter(p["topic"] for p in posts)
    issue = topics.most_common(1)[0][0] if topics else ""
    names = ", ".join(f"{t} {n}건" for t, n in topics.most_common(3))
    who = "우리 학원" if company["role"] == "ours" else "경쟁사"
    summary = f"{who} 기준 {len(posts)}건 확인. 주제는 {names}입니다." if posts else ""
    highlight = " / ".join(p["title"][:40] for p in posts[:2])
    return {"issue": issue, "summary": summary, "highlight": highlight}


def day_digest(repo: Repo, date: str, use_ai: bool = True) -> dict[str, dict]:
    """그날 게시물이 있는 회사별 요약을 만들어 저장. 반환: {company_id: {...}}"""
    companies = {c["id"]: c for c in repo.companies()}
    posts = [p for p in repo.posts(date, date) if p["company_id"] in companies]
    by_c: dict[str, list[dict]] = {}
    for p in posts:
        by_c.setdefault(p["company_id"], []).append(p)
    if not by_c:
        return {}
    result = {cid: rule_digest(companies[cid], ps) | {"model": "규칙"} for cid, ps in by_c.items()}
    if use_ai:
        prefer, models = _ai_cfg(repo)
        data = [{"id": cid, "name": companies[cid]["name"], "구분": "우리 학원" if companies[cid]["role"] == "ours" else "경쟁사",
                 "게시물": [_post_brief(p) for p in ps[:8]]} for cid, ps in by_c.items()]
        prompt = (f"리서치 기준: {_goal(repo)}\n날짜: {date}\n\n<data>\n{json.dumps(data, ensure_ascii=False)}\n</data>\n\n"
                  "회사별로 JSON 만 출력하세요: {\"companies\":[{\"id\":\"...\",\"issue\":\"중심 이슈(8자 이내 명사구)\","
                  "\"summary\":\"2~3문장 요약\",\"highlight\":\"핵심 요약 한 문장\"}]}")
        text, label = llm.complete(prompt, SYSTEM, prefer, models)
        parsed = llm.extract_json(text) or {}
        for item in (parsed.get("companies") if isinstance(parsed, dict) else None) or []:
            cid = item.get("id")
            if cid in result and item.get("summary"):
                result[cid] = {"issue": str(item.get("issue", ""))[:30], "summary": str(item["summary"])[:600],
                               "highlight": str(item.get("highlight", ""))[:300], "model": label}
    for cid, d in result.items():
        repo.set_day_summary(date, cid, d["issue"], d["summary"], d["highlight"], d["model"])
    return result


# ---------- 주간/월간 분석 ----------
def _top_posts(repo: Repo, start: str, end: str, cid: str, n: int = 5) -> list[dict]:
    return [{"title": p["title"], "url": p["url"], "topic": p["topic"], "date": p["post_date"], "platform": p["platform"]}
            for p in repo.posts(start, end, company_id=cid, limit=n)]


def build_stats(repo: Repo, kind: str, start: str, end: str) -> dict:
    cur = period_stats(repo, start, end)
    ps, pe = previous_period(start, end)
    prev = period_stats(repo, ps, pe)
    prev_by = {c["id"]: c["total"] for c in prev["companies"]}
    for c in cur["companies"]:
        c["prev"] = prev_by.get(c["id"], 0)
        c["top"] = _top_posts(repo, start, end, c["id"])
    aeo = None
    days = [d for d in repo.aeo_days() if start <= d["date"] <= end]
    if days:
        last = repo.aeo_day(days[-1]["date"]) or {}
        k = last.get("kpi", {})
        aeo = {"date": days[-1]["date"], "todayRate": k.get("today_rate"), "windowRate": k.get("target_rate"),
               "officialRate": k.get("official_cited_rate"),
               "sov": [{"name": s["name"], "rate": s["rate"]} for s in (last.get("sov") or [])[:6]],
               "topAction": (last.get("actions") or [{}])[0].get("title", "")}
    return {"kind": kind, "start": start, "end": end, "total": cur["total"], "prevTotal": prev["total"],
            "byTopic": cur["byTopic"], "byPlatform": cur["byPlatform"], "companies": cur["companies"], "aeo": aeo}


def rule_sections(stats: dict) -> tuple[str, list[dict]]:
    cs = stats["companies"]
    ours = next((c for c in cs if c["role"] == "ours"), None)
    comps = sorted((c for c in cs if c["role"] != "ours"), key=lambda c: -c["total"])
    headline = f"{stats['start'][5:]} ~ {stats['end'][5:]} 수집 게시물 {stats['total']}건 (직전 기간 {stats['prevTotal']}건)"
    glance = [f"전체 {stats['total']}건 — 직전 기간 대비 {stats['total'] - stats['prevTotal']:+d}건."]
    if ours:
        glance.append(f"우리 학원 {ours['total']}건 (직전 {ours['prev']}건).")
    if comps and comps[0]["total"]:
        top = comps[0]
        tt = Counter(top["byTopic"]).most_common(1)
        glance.append(f"가장 활발한 경쟁사: {top['name']} {top['total']}건" + (f" (주제 {tt[0][0]})." if tt else "."))
    sections = [{"title": "한눈에 보기", "bullets": glance}]
    cm = []
    for c in comps:
        if not c["total"]:
            cm.append(f"{c['name']}: 새 게시물 없음.")
            continue
        tt = ", ".join(f"{t} {n}" for t, n in Counter(c["byTopic"]).most_common(2))
        title = c["top"][0]["title"][:45] if c["top"] else ""
        cm.append(f"{c['name']}: {c['total']}건 ({tt}) — 대표 게시물 “{title}”")
    if cm:
        sections.append({"title": "경쟁사 움직임", "bullets": cm})
    if ours:
        theirs = Counter()
        for c in comps:
            theirs.update(c["byTopic"])
        gap = [t for t, n in theirs.most_common() if n >= 2 and ours["byTopic"].get(t, 0) == 0][:3]
        tips = []
        if gap:
            tips.append(f"경쟁사가 다룬 주제 중 우리 학원 게시물이 없는 것: {', '.join(gap)}.")
        if ours["total"] == 0:
            tips.append("우리 학원 신규 게시물이 없습니다. 최소 주 2회 게시를 권장합니다.")
        if tips:
            sections.append({"title": "시사점", "bullets": tips})
    if stats.get("aeo") and stats["aeo"].get("windowRate") is not None:
        a = stats["aeo"]
        sections.append({"title": "AI 챗봇 언급", "bullets": [
            f"AI 답변 속 이천캠퍼스 언급률 {a['windowRate']}% (측정일 {a['date']}), 공식 홈페이지 인용률 {a['officialRate']}%."
            + (f" 최우선 과제: {a['topAction']}." if a["topAction"] else "")]})
    return headline, sections


def generate_report(repo: Repo, kind: str, anchor: str, use_ai: bool = True) -> dict:
    start, end = period_range(kind, anchor)
    stats = build_stats(repo, kind, start, end)
    headline, sections = rule_sections(stats)
    model = "규칙"
    if use_ai and stats["total"]:
        prefer, models = _ai_cfg(repo)
        slim = {k: v for k, v in stats.items() if k != "companies"}
        slim["companies"] = [{"name": c["name"], "구분": "우리 학원" if c["role"] == "ours" else "경쟁사", "건수": c["total"],
                              "직전": c["prev"], "주제": c["byTopic"], "채널": c["byPlatform"],
                              "대표 게시물": [t["title"] for t in c["top"]]} for c in stats["companies"]]
        prompt = (f"리서치 기준: {_goal(repo)}\n분석 기간: {start} ~ {end} ({'주간' if kind == 'week' else '월간'})\n\n"
                  f"<data>\n{json.dumps(slim, ensure_ascii=False)}\n</data>\n\n"
                  "JSON 만 출력하세요: {\"headline\":\"한 줄 결론\",\"sections\":[{\"title\":\"한눈에 보기\",\"bullets\":[...]},"
                  "{\"title\":\"경쟁사 움직임\",\"bullets\":[...]},{\"title\":\"우리 학원 vs 경쟁사\",\"bullets\":[...]},"
                  "{\"title\":\"시사점·제안\",\"bullets\":[...]}]} 각 bullets 는 2~4개, 수치는 데이터에 있는 값만 사용.")
        text, label = llm.complete(prompt, SYSTEM, prefer, models)
        parsed = llm.extract_json(text)
        if isinstance(parsed, dict) and parsed.get("sections"):
            secs = [{"title": str(s.get("title", ""))[:30], "bullets": [str(b)[:300] for b in (s.get("bullets") or [])][:6]}
                    for s in parsed["sections"] if isinstance(s, dict)]
            if any(s["bullets"] for s in secs):
                headline, sections, model = str(parsed.get("headline") or headline)[:200], secs, label
    payload = {"stats": stats, "headline": headline, "sections": sections, "model": model,
               "generatedAt": now_kst().isoformat(timespec="minutes")}
    repo.set_report(kind, start, end, payload, model)
    return payload


def auto_reports(repo: Repo, today: str) -> list[str]:
    """월요일이면 지난주, 1일이면 지난달 분석을 만든다."""
    made = []
    from ..timeutil import to_date
    d = to_date(today)
    if d.weekday() == 0:
        a = shift_period("week", today, -1)
        if not repo.report("week", period_range("week", a)[0]):
            generate_report(repo, "week", a)
            made.append("주간")
    if d.day == 1:
        a = shift_period("month", today, -1)
        if not repo.report("month", period_range("month", a)[0]):
            generate_report(repo, "month", a)
            made.append("월간")
    return made


# ---------- 챗봇 / 리서치 기준 ----------
def chat_context(repo: Repo) -> dict:
    today = now_kst().strftime("%Y-%m-%d")
    start, end = period_range("week", today)
    s14 = shift_period("day", today, -13)
    st = period_stats(repo, s14, today)
    posts = repo.posts(s14, today, limit=40)
    ctx = {"오늘": today, "리서치 기준": _goal(repo),
           "최근14일 회사별 건수": {c["name"] + ("(우리)" if c["role"] == "ours" else ""): c["total"] for c in st["companies"]},
           "주제별": {t["topic"]: t["n"] for t in st["byTopic"]},
           "최근 게시물": [{"회사": p["company_name"], "날짜": p["post_date"], "제목": p["title"], "주제": p["topic"]} for p in posts]}
    days = repo.aeo_days()
    if days:
        last = repo.aeo_day(days[-1]["date"]) or {}
        ctx["AI 언급"] = {"측정일": days[-1]["date"], "kpi": {k: last.get("kpi", {}).get(k) for k in ("today_rate", "target_rate", "official_cited_rate")},
                         "학원별 언급률": [{"name": s["name"], "rate": s["rate"]} for s in (last.get("sov") or [])[:8]],
                         "개선과제": [a["title"] for a in (last.get("actions") or [])[:4]]}
    return ctx


def answer_chat(repo: Repo, messages: list[dict]) -> tuple[str, str]:
    prefer, models = _ai_cfg(repo)
    hist = "\n".join(f"{'사용자' if m.get('role') == 'user' else 'AI'}: {str(m.get('content', ''))[:1500]}" for m in messages[-8:])
    prompt = (f"<data>\n{json.dumps(chat_context(repo), ensure_ascii=False)}\n</data>\n\n대화:\n{hist}\n\n"
              "위 데이터만 근거로 마지막 사용자 질문에 한국어로 간결히 답하세요. 데이터에 없으면 없다고 말하세요.")
    text, label = llm.complete(prompt, SYSTEM, prefer, models)
    return text or "AI 모델 키(GEMINI_API_KEY 등)가 설정되지 않았거나 응답을 받지 못했습니다.", label


GOAL_FALLBACK = [
    {"title": "자사와 경쟁사 흐름 비교", "desc": "이 기준에 맞춰 경쟁사 변화와 업계 흐름을 구분합니다."},
    {"title": "경쟁사 모집·일정 변화 추적", "desc": "설명회, 모집 마감, 윈터스쿨 등 일정성 게시물을 우선 봅니다."},
    {"title": "합격 실적·콘텐츠 홍보 비교", "desc": "합격 실적과 콘텐츠 발행 빈도·주제를 자사와 비교합니다."},
]


def suggest_goals(repo: Repo) -> list[dict]:
    prefer, models = _ai_cfg(repo)
    prompt = (f"<data>\n{json.dumps(chat_context(repo), ensure_ascii=False)}\n</data>\n\n현재 데이터를 보고 기숙학원 마케팅 담당자가 "
              "매일 확인하면 좋을 리서치 기준 3개를 JSON 배열로만 출력: [{\"title\":\"15자 이내\",\"desc\":\"한 문장\"}]")
    text, _ = llm.complete(prompt, SYSTEM, prefer, models)
    parsed = llm.extract_json(text)
    if isinstance(parsed, list):
        out = [{"title": str(g.get("title", ""))[:40], "desc": str(g.get("desc", ""))[:160]} for g in parsed
               if isinstance(g, dict) and g.get("title")]
        if out:
            return out[:3]
    return GOAL_FALLBACK
