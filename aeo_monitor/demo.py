"""화면 미리보기용 가짜 데이터 (실제 수집값이 아님). 운영 DB에는 쓰지 마세요 — AEO_DATA_DIR 를 따로 지정해 실행합니다."""
from __future__ import annotations

import random
from datetime import timedelta

from .content import ai as content_ai
from .content.classify import classify
from .pipeline import run_aeo
from .repo import Repo
from .seed import seed_defaults
from .storage import Store
from .timeutil import now_kst, today_kst

TITLES = {
    "이투스247 이천기숙학원": ["2027 윈터스쿨 모집 안내", "이천 기숙 생활관리 하루 일과 공개", "수능 D-{d} 학습 스케줄 가이드", "이달의 급식 식단표", "면학 분위기 우수반 인터뷰", "합격 수기: 서울대 의예과 합격 후기"],
    "강남대성 기숙학원(퀘타)": ["[D-{d}] 퀘타 의대관 X 농심 보노스프 간식 이벤트", "숫자로 증명하는 합격 신화 | 의치한약수 입결", "의대생들은 수능 D-{d}에 '이것' 했습니다", "2027 윈터스쿨 수업 안내", "재원생 응원 선물 이벤트"],
    "메가스터디 기숙학원(러셀)": ["러셀 기숙 2027 모집 설명회 일정", "수학 클리닉 커리큘럼 공개", "과거로 돌아간다면 1997학년도 수능 풀기", "기숙사 시설 투어 영상"],
    "시대인재 기숙학원": ["시대인재 재수종합 정시 입결 분석", "[모집] 겨울방학 특강 접수 시작", "국어 학습법 특강 안내"],
}


def seed_demo(store: Store, days: int = 45, seed: int = 7) -> None:
    repo = Repo(store)
    seed_defaults(repo)
    rnd = random.Random(seed)
    today = today_kst()
    comps = {c["name"]: c for c in repo.companies()}
    for i, (name, titles) in enumerate(TITLES.items()):
        c = comps[name]
        platforms = [("blog", f"https://blog.naver.com/demo_{i}"), ("youtube", f"https://www.youtube.com/@demo{i}"),
                     ("homepage", f"https://demo{i}.example.kr")]
        chids = {}
        for typ, url in platforms:
            chid = repo.add_channel(c["id"], typ, url)
            chids[typ] = chid
            bad = (i == 2 and typ == "homepage")
            repo.update_channel(chid, status="login" if bad else "ok",
                                status_msg="접근이 거부되었습니다 (HTTP 403). 로그인이 필요하거나 수집이 차단된 페이지입니다." if bad else "구조화된 항목을 수집했습니다.",
                                last_checked_at=now_kst().isoformat(timespec="seconds"), item_count=0 if bad else 20)
        for d in range(days):
            day = (now_kst() - timedelta(days=d)).strftime("%Y-%m-%d")
            for _ in range(rnd.choice([0, 0, 1, 1, 2]) if c["role"] != "ours" or d % 2 else rnd.choice([0, 1])):
                t = rnd.choice(titles).format(d=rnd.randint(30, 60))
                typ = rnd.choice(["blog", "blog", "youtube", "homepage"])
                if i == 2 and typ == "homepage":
                    typ = "blog"
                repo.upsert_post(company_id=c["id"], channel_id=chids[typ], platform=typ, url=f"https://example.com/{i}/{d}/{rnd.randint(1, 10**6)}",
                                 title=t, snippet=f"{t} — 자세한 내용은 원문에서 확인하세요. 상담과 설명회 일정이 함께 안내되었습니다.", body=t,
                                 topic=classify(t), published_at=f"{day}T10:00:00+09:00", post_date=day)
    store.conn.commit()
    for d in (today, (now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")):
        content_ai.day_digest(repo, d, use_ai=False)
    repo.kv_set("aeo", {**repo.kv_get("aeo", {}), "engines": ["mock"]})
    for k in range(6, 0, -1):
        import os
        os.environ["AEO_MOCK_SEED"] = str(k)
        run_aeo(repo, run_date=(now_kst() - timedelta(days=k - 1)).strftime("%Y-%m-%d"), engines_override=["mock"])
    # 미리보기 전용 DB 이므로 모의 측정도 일반 결과처럼 보이게 한다
    store.conn.execute("UPDATE runs SET demo=0")
    store.conn.execute("UPDATE aeo_days SET demo=0")
    store.conn.commit()
    content_ai.generate_report(repo, "week", today, use_ai=False)
    j = repo.create_job("all", "schedule")
    repo.update_job(j, status="done", progress="완료")
