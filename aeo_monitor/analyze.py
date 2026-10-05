"""한 번의 실행 결과를 집계하고, 언급/미언급 원인을 진단해 AEO/GEO 개선과제를 만든다."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta

from .config import BrandConfig
from .sources import COMPETITOR, OFFICIAL
from .storage import Store

COMMUNITY = "커뮤니티(수만휘·오르비 등)"
PRESS = "언론/보도자료"
THIRD = "제3자 학원정보 플랫폼"
OWN_TYPES = {OFFICIAL, "자사(앱)", "자사(기타 채널)"}

# ---- 원인 코드 ----
REASONS = {
    # 언급된 이유
    "M_BRANDED_QUERY": "질문에 '이투스' 브랜드명이 포함되어 있어 언급됨",
    "M_SOURCE_MENTIONS_TARGET": "검색된 출처 문서가 이천캠퍼스를 직접 다룸",
    "M_OFFICIAL_CITED": "공식 홈페이지(이천캠퍼스)가 출처로 인용됨",
    "M_COMMUNITY_CITED": "커뮤니티 후기가 출처로 인용됨",
    "M_PRESS_CITED": "언론/보도자료가 출처로 인용됨",
    "M_THIRD_PARTY_CITED": "제3자 학원정보 플랫폼이 출처로 인용됨",
    "M_MODEL_KNOWLEDGE": "이천캠퍼스를 다룬 출처 없이 모델 사전지식으로 언급됨",
    # 언급되지 않은 이유
    "N_COMPETITORS_INSTEAD": "경쟁 기숙학원만 언급됨 (추천·비교 목록에서 밀림)",
    "N_CAMPUS_CONFUSION": "'이투스247' 브랜드/타 캠퍼스만 언급되고 이천캠퍼스는 빠짐",
    "N_GENERIC_ANSWER": "학원명 없이 일반론으로 답변됨",
    "N_NO_TARGET_SOURCE": "AI가 찾은 출처 중 이천캠퍼스를 다룬 문서가 없음",
    "N_OFFICIAL_MISSING": "공식 홈페이지(이천캠퍼스)가 출처로 잡히지 않음",
    "N_COMMUNITY_MISSING": "커뮤니티 후기(원 질문 채널)가 출처로 잡히지 않음",
    "N_ERROR": "엔진 오류/거절로 답변 없음",
    # 공통
    "X_NEGATIVE": "부정적 맥락으로 언급됨",
    "X_LOW_RANK": "언급됐지만 3번째 이후로 밀림",
}

# ---- 원인 → 개선과제 ----
ACTIONS = {
    "N_OFFICIAL_MISSING": {
        "title": "공식 홈페이지를 AI가 인용할 수 있는 형태로 보강",
        "area": "자사 채널(On-site)",
        "detail": [
            "이천캠퍼스 전용 URL을 만들고 학원비·급식·시설·생활관리·커리큘럼·입소일정을 이미지가 아닌 HTML 텍스트로 게시",
            "소비자 실제 질문(이 리포트의 질문 목록)을 그대로 제목으로 한 FAQ 페이지 + schema.org FAQPage / EducationalOrganization 구조화 데이터",
            "robots.txt 에서 GPTBot·OAI-SearchBot·ClaudeBot·PerplexityBot·Google-Extended·Yeti(네이버) 허용 확인, sitemap 을 구글 서치콘솔·네이버 서치어드바이저에 제출",
        ],
    },
    "N_CAMPUS_CONFUSION": {
        "title": "'이투스247 이천기숙학원' 캠퍼스 명칭·고유 정보 일관화",
        "area": "엔티티 정합성",
        "detail": [
            "보도자료·플랫폼·앱 설명에 항상 '이투스247 이천기숙학원(경기 이천시)' 정식 명칭과 주소를 함께 표기",
            "안성·광주(독학기숙)·송파 등 타 캠퍼스와 구분되는 고유 사실(정원, 위치, 관리 방식, 개원 연도, 합격 실적)을 한 문서에 정리",
            "나무위키 등 백과형 문서에 캠퍼스별 항목 분리/보완",
        ],
    },
    "N_COMPETITORS_INSTEAD": {
        "title": "추천·비교형 질문에 대응하는 비교 콘텐츠 확보",
        "area": "오프사이트(Off-site)",
        "detail": [
            "'수도권 재수 기숙학원 비교' 처럼 여러 학원을 표로 비교하는 콘텐츠에 이천캠퍼스가 포함되도록 언론·교육 매체 기고/보도",
            "경쟁사가 언급될 때 인용된 출처 도메인(아래 '경쟁사 언급 시 출처')에 이천캠퍼스 정보 등록",
            "강점(관리·시설·급식 등)을 수치·사실 위주로 서술해 AI가 비교표에 넣기 쉽게 만들기",
        ],
    },
    "N_NO_TARGET_SOURCE": {
        "title": "AI가 실제로 검색하는 출처에 이천캠퍼스 정보 배치",
        "area": "오프사이트(Off-site)",
        "detail": [
            "이 리포트의 '많이 인용되는 도메인' 상위 사이트(언론·학원정보 플랫폼)에 이천캠퍼스 정보를 최신으로 등록/배포",
            "보도자료 제목·첫 문단에 '이투스247 이천기숙학원'과 질문 키워드(후기, 급식, 시설, 비용 등)를 포함",
        ],
    },
    "N_GENERIC_ANSWER": {
        "title": "일반 질문(학원명 없는 질문)용 가이드 콘텐츠 발행",
        "area": "콘텐츠",
        "detail": [
            "'재수 기숙학원 고르는 기준', '재수 비용', '반수 기숙 시기' 같은 정보형 가이드를 발행하고 사례로 이천캠퍼스를 포함",
            "질문 원문 표현(구어체)을 소제목으로 활용해 AI 답변의 근거 문서가 되도록 구성",
        ],
    },
    "N_COMMUNITY_MISSING": {
        "title": "커뮤니티 후기를 공개 웹 문서로 확장",
        "area": "UGC/후기",
        "detail": [
            "네이버 카페(수만휘 등) 글은 로그인·크롤링 제한으로 AI 인용이 거의 되지 않음",
            "재원생/수료생 후기를 네이버 블로그·티스토리·공식 후기 페이지 등 공개 웹에 게시되도록 유도",
            "오르비(공개 게시판)에서 질문 받기·Q&A 등 공개 답변 활동",
        ],
    },
    "X_NEGATIVE": {
        "title": "부정 맥락 언급 대응",
        "area": "평판",
        "detail": [
            "부정 스니펫의 주제(급식·시설·관리 등)를 확인하고 개선 사실을 공식 공지/보도자료로 공개",
            "최근 개선사항을 날짜와 함께 기재해 최신 정보가 우선 인용되도록",
        ],
    },
    "X_LOW_RANK": {
        "title": "추천 목록 내 노출 순위 개선",
        "area": "콘텐츠",
        "detail": [
            "비교 기사·리스트형 콘텐츠에서 상위에 배치될 수 있도록 대표 강점 1~2개를 명확히 정의해 반복 노출",
        ],
    },
}


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def diagnose(resp: dict, brands: BrandConfig) -> list[str]:
    """한 답변에 대한 원인 코드 목록."""
    if resp["error"] and not resp["answer"]:
        return ["N_ERROR"]
    target = resp["mentions"].get(brands.target_id, {})
    cites = resp["citations"]
    types = {c["source_type"] for c in cites}
    target_srcs = [c for c in cites if c["mentions_target"]]
    codes: list[str] = []
    if target.get("mentioned"):
        if resp["branded"]:
            codes.append("M_BRANDED_QUERY")
        if target_srcs:
            codes.append("M_SOURCE_MENTIONS_TARGET")
            ttypes = {c["source_type"] for c in target_srcs} | types
        else:
            ttypes = types
        if OFFICIAL in types:
            codes.append("M_OFFICIAL_CITED")
        if COMMUNITY in ttypes:
            codes.append("M_COMMUNITY_CITED")
        if PRESS in ttypes:
            codes.append("M_PRESS_CITED")
        if THIRD in ttypes:
            codes.append("M_THIRD_PARTY_CITED")
        if not target_srcs and OFFICIAL not in types:
            codes.append("M_MODEL_KNOWLEDGE")
        if target.get("sentiment") in ("negative", "mixed"):
            codes.append("X_NEGATIVE")
        if (target.get("rank") or 0) >= 3:
            codes.append("X_LOW_RANK")
    else:
        comps = [b for b, m in resp["mentions"].items() if m["mentioned"] and b != brands.target_id]
        if resp["group_only"] or resp["other_campus"]:
            codes.append("N_CAMPUS_CONFUSION")
        if comps:
            codes.append("N_COMPETITORS_INSTEAD")
        if not comps and not resp["group_only"]:
            codes.append("N_GENERIC_ANSWER")
        if not target_srcs:
            codes.append("N_NO_TARGET_SOURCE")
    if OFFICIAL not in types:
        codes.append("N_OFFICIAL_MISSING")
    if COMMUNITY not in types:
        codes.append("N_COMMUNITY_MISSING")
    return codes


def load_run(store: Store, run_id: int) -> list[dict]:
    resps = {r["id"]: dict(r) for r in store.responses(run_id)}
    for r in resps.values():
        r["categories"] = json.loads(r["categories"] or "[]")
        r["other_campus"] = json.loads(r["other_campus"] or "[]")
        r["mentions"] = {}
        r["citations"] = []
    for m in store.mentions(run_id):
        resps[m["response_id"]]["mentions"][m["brand_id"]] = dict(m)
    for c in store.citations(run_id):
        resps[c["response_id"]]["citations"].append(dict(c))
    return list(resps.values())


def _target_rate(resps: list[dict], target_id: str) -> tuple[int, int]:
    valid = [r for r in resps if r["answer"]]
    hit = sum(1 for r in valid if r["mentions"].get(target_id, {}).get("mentioned"))
    return hit, len(valid)


def analyze_run(store: Store, run_id: int, brands: BrandConfig, baseline: dict | None = None,
                trend_days: int = 14) -> dict:
    run = dict(store.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
    resps = load_run(store, run_id)
    tid = brands.target_id
    for r in resps:
        r["reasons"] = diagnose(r, brands)

    core = [r for r in resps if r["origin"] != "template"]  # 엑셀 기반 실제 소비자 질문
    tpl = [r for r in resps if r["origin"] == "template"]  # 학원별 동일 질문
    valid_core = [r for r in core if r["answer"]]

    hit, n = _target_rate(core, tid)
    kpi = {
        "responses": len(resps),
        "core_responses": n,
        "errors": sum(1 for r in resps if r["error"] and not r["answer"]),
        "target_mentions": hit,
        "target_rate": _pct(hit, n),
        "brand_only": sum(1 for r in valid_core if r["group_only"]),
        "brand_only_rate": _pct(sum(1 for r in valid_core if r["group_only"]), n),
        "campus_confusion": sum(1 for r in valid_core if r["other_campus"]),
        "official_cited_rate": _pct(sum(1 for r in valid_core if any(c["source_type"] == OFFICIAL for c in r["citations"])), n),
        "avg_rank": None,
    }
    ranks = [r["mentions"][tid]["rank"] for r in valid_core if r["mentions"].get(tid, {}).get("mentioned")]
    if ranks:
        kpi["avg_rank"] = round(sum(ranks) / len(ranks), 2)
    sent = Counter(r["mentions"][tid]["sentiment"] for r in valid_core if r["mentions"].get(tid, {}).get("mentioned"))
    kpi["sentiment"] = dict(sent)

    # 엔진별 / 카테고리별 / 브랜드 질의 여부별
    def rate_by(key_fn) -> list[dict]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in core:
            for k in key_fn(r):
                groups[k].append(r)
        out = []
        for k, rs in groups.items():
            h, d = _target_rate(rs, tid)
            out.append({"key": k, "hit": h, "n": d, "rate": _pct(h, d)})
        return sorted(out, key=lambda x: (-x["n"], x["key"]))

    by_engine = rate_by(lambda r: [r["engine"]])
    by_category = rate_by(lambda r: r["categories"] or ["(TOP30 질문)"])
    by_branded = rate_by(lambda r: ["브랜드 포함 질문" if r["branded"] else "일반 질문(브랜드 없음)"])

    # 경쟁사 점유율 (동일한 실제 질문 세트에서)
    sov = []
    total_m = 0
    for b in brands.brands:
        ms = [r["mentions"].get(b.id, {}) for r in valid_core]
        cnt = sum(1 for m in ms if m.get("mentioned"))
        ranks_b = [m["rank"] for m in ms if m.get("mentioned")]
        first = sum(1 for m in ms if m.get("rank") == 1)
        total_m += cnt
        sov.append({"id": b.id, "name": b.name, "mentions": cnt, "rate": _pct(cnt, len(valid_core)),
                    "first": first, "avg_rank": round(sum(ranks_b) / len(ranks_b), 2) if ranks_b else None,
                    "is_target": b.id == tid})
    for s in sov:
        s["share"] = _pct(s["mentions"], total_m)
    sov.sort(key=lambda s: (-s["mentions"], s["name"]))

    # 학원별 동일 질문 비교
    tpl_cmp = defaultdict(lambda: {"n": 0, "self": 0, "official": 0, "cites": 0, "types": Counter(), "others": Counter()})
    for r in tpl:
        if not r["answer"]:
            continue
        row = tpl_cmp[r["brand_scope"]]
        row["n"] += 1
        if r["mentions"].get(r["brand_scope"], {}).get("mentioned"):
            row["self"] += 1
        own_domains = brands.by_id(r["brand_scope"]).domains
        if any(any(d.lower() in c["url"].lower() for d in own_domains if d) for c in r["citations"]):
            row["official"] += 1
        row["cites"] += len(r["citations"])
        row["types"].update(c["source_type"] for c in r["citations"])
        for b, m in r["mentions"].items():
            if m["mentioned"] and b != r["brand_scope"]:
                row["others"][b] += 1
    template_compare = []
    for bid, row in tpl_cmp.items():
        b = brands.by_id(bid)
        template_compare.append({
            "id": bid, "name": b.name, "is_target": bid == tid, "n": row["n"],
            "self_rate": _pct(row["self"], row["n"]),
            "official_rate": _pct(row["official"], row["n"]),
            "avg_cites": round(row["cites"] / row["n"], 1) if row["n"] else 0,
            "top_types": row["types"].most_common(3),
            "cross_mentions": [(brands.by_id(k).name, v) for k, v in row["others"].most_common(3)],
        })
    template_compare.sort(key=lambda x: (-x["self_rate"], x["name"]))

    # 출처 분석
    def type_mix(rs: list[dict], cited_only: bool = False) -> dict:
        c = Counter()
        for r in rs:
            for x in r["citations"]:
                if cited_only and not x["cited_in_answer"]:
                    continue
                c[x["source_type"]] += 1
        return dict(c)

    mentioned = [r for r in valid_core if r["mentions"].get(tid, {}).get("mentioned")]
    not_mentioned = [r for r in valid_core if not r["mentions"].get(tid, {}).get("mentioned")]
    comp_mentioned = [r for r in not_mentioned if any(m["mentioned"] for b, m in r["mentions"].items() if b != tid)]

    def top_domains(rs: list[dict], k: int = 10, only_target: bool = False) -> list[tuple]:
        c = Counter()
        types = {}
        for r in rs:
            for x in r["citations"]:
                if only_target and not x["mentions_target"]:
                    continue
                c[x["domain"]] += 1
                types[x["domain"]] = x["source_type"]
        return [(d, n, types[d]) for d, n in c.most_common(k)]

    sources = {
        "mix_all": type_mix(valid_core),
        "mix_cited": type_mix(valid_core, cited_only=True),
        "mix_when_mentioned": type_mix(mentioned),
        "mix_when_not": type_mix(not_mentioned),
        "top_domains": top_domains(valid_core, 15),
        "target_source_domains": top_domains(valid_core, 15, only_target=True),
        "domains_when_competitor": top_domains(comp_mentioned, 10),
        "baseline": (baseline or {}).get("source_mix"),
        "baseline_label": (baseline or {}).get("label"),
    }

    # 원인 집계
    reason_counts_m = Counter()
    reason_counts_n = Counter()
    for r in valid_core:
        target_on = r["mentions"].get(tid, {}).get("mentioned")
        for code in r["reasons"]:
            if target_on and code[0] in "MX":
                reason_counts_m[code] += 1
            elif not target_on and code[0] == "N":
                reason_counts_n[code] += 1

    # 개선과제 (원인 빈도 × 가중치)
    weights = {"N_OFFICIAL_MISSING": 1.0, "N_CAMPUS_CONFUSION": 1.6, "N_COMPETITORS_INSTEAD": 1.5,
               "N_NO_TARGET_SOURCE": 1.3, "N_GENERIC_ANSWER": 0.8, "N_COMMUNITY_MISSING": 0.6,
               "X_NEGATIVE": 1.4, "X_LOW_RANK": 0.7}
    all_counts = Counter(code for r in valid_core for code in r["reasons"])
    actions = []
    for code, a in ACTIONS.items():
        cnt = all_counts.get(code, 0)
        if not cnt:
            continue
        examples = [r["question"] for r in valid_core if code in r["reasons"]]
        examples = list(dict.fromkeys(examples))[:3]
        actions.append({**a, "code": code, "reason": REASONS[code], "count": cnt,
                        "share": _pct(cnt, len(valid_core)), "score": round(cnt * weights.get(code, 1.0), 1),
                        "examples": examples})
    actions.sort(key=lambda a: -a["score"])
    for i, a in enumerate(actions, 1):
        a["priority"] = "높음" if i <= 2 else ("중간" if i <= 4 else "낮음")

    # 질문별 상세
    questions = defaultdict(lambda: {"question": "", "categories": [], "branded": False, "views": 0, "engines": {}})
    for r in core:
        q = questions[r["question_id"]]
        q["question"], q["categories"], q["branded"] = r["question"], r["categories"], bool(r["branded"])
        m = r["mentions"].get(tid, {})
        comps = [brands.by_id(b).name for b, x in sorted(r["mentions"].items(), key=lambda kv: kv[1].get("rank") or 99)
                 if x["mentioned"] and b != tid]
        prev = q["engines"].get(r["engine"])
        entry = {
            "mentioned": bool(m.get("mentioned")), "rank": m.get("rank"), "sentiment": m.get("sentiment"),
            "brand_only": bool(r["group_only"]), "other_campus": r["other_campus"], "error": r["error"],
            "competitors": comps[:5],
            "sources": [(c["domain"], c["source_type"], c["url"], bool(c["mentions_target"])) for c in r["citations"]][:8],
            "reasons": [x for x in r["reasons"] if x not in ("N_OFFICIAL_MISSING", "N_COMMUNITY_MISSING")],
            "snippet": m.get("snippet") or "",
        }
        if prev is None or (entry["mentioned"] and not prev["mentioned"]):
            q["engines"][r["engine"]] = entry
    question_rows = sorted(questions.values(), key=lambda q: (sum(e["mentioned"] for e in q["engines"].values()), q["question"]))

    # 전일 대비 / 추이
    prev = store.previous_run(store.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
    delta = None
    if prev:
        p_core = [r for r in load_run(store, prev["id"]) if r["origin"] != "template"]
        ph, pn = _target_rate(p_core, tid)
        delta = {"date": prev["run_date"], "rate": _pct(ph, pn), "diff": round(kpi["target_rate"] - _pct(ph, pn), 1)}
    end = date.fromisoformat(run["run_date"])
    trend = []
    for tr in store.runs_between((end - timedelta(days=trend_days - 1)).isoformat(), end.isoformat(), run["demo"]):
        t_core = [r for r in load_run(store, tr["id"]) if r["origin"] != "template"]
        th, tn = _target_rate(t_core, tid)
        per_engine = {}
        for e in {r["engine"] for r in t_core}:
            eh, en = _target_rate([r for r in t_core if r["engine"] == e], tid)
            per_engine[e] = _pct(eh, en)
        trend.append({"date": tr["run_date"], "rate": _pct(th, tn), "engines": per_engine})

    return {
        "run": run, "target": brands.target.name, "kpi": kpi, "delta": delta, "trend": trend,
        "by_engine": by_engine, "by_category": by_category, "by_branded": by_branded,
        "sov": sov, "template_compare": template_compare, "sources": sources,
        "reasons_mentioned": [(REASONS[k], v, k) for k, v in reason_counts_m.most_common()],
        "reasons_not": [(REASONS[k], v, k) for k, v in reason_counts_n.most_common()],
        "actions": actions, "questions": question_rows,
        "engines": sorted({r["engine"] for r in resps}),
    }
