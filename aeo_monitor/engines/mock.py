"""모의(데모) 엔진: API 키 없이 파이프라인/리포트를 시험하기 위한 결정적 가짜 답변.

실제 측정값이 아니며, 이 엔진으로 만든 리포트에는 'DEMO' 표시가 붙습니다.
"""
from __future__ import annotations

import hashlib
import random

from .base import Citation, Engine, EngineResult

_BRANDS = ["이투스247 이천", "강남대성 퀘타", "러셀 기숙학원", "이천 청솔", "시대인재 기숙", "잇올", "비상에듀 기숙학원", "이투스247 안성"]
_SOURCES = [
    ("https://www.dhnews.co.kr/news/articleView.html?idxno=1", "이투스247학원 송파, 재수정규반 모집"),
    ("https://academy.prompie.com/academy/123", "이투스247 기숙학원 정보"),
    ("https://apps.apple.com/kr/app/etoos/id1", "이투스 247 앱"),
    ("https://cafe.naver.com/suhui/29253553", "다녔던 기숙학원 장단점 정리"),
    ("https://orbi.kr/00076376924", "재수 학원"),
    ("https://blog.naver.com/someone/2233", "기숙학원 비교 후기"),
    ("https://namu.wiki/w/기숙학원", "기숙학원 - 나무위키"),
    ("https://www.megastudy.net/russel", "메가스터디 러셀 기숙"),
    ("https://www.veritas-a.com/news/1", "2027 재수 기숙학원 선택법"),
]


class MockEngine(Engine):
    name = "mock"
    default_model = "demo"

    def __init__(self, model: str | None = None, seed: str = ""):
        super().__init__(model)
        self.seed = seed

    def ask(self, question: str) -> EngineResult:
        h = int(hashlib.sha256((self.seed + question).encode()).hexdigest(), 16)
        rnd = random.Random(h)
        brands = rnd.sample(_BRANDS, rnd.randint(0, 4))
        if "이투스" in question and rnd.random() < 0.6 and "이투스247 이천" not in brands:
            brands.insert(0, "이투스247 이천")
        lines = [f"'{question}'에 대한 답변입니다."]
        for b in brands:
            tone = rnd.choice(["관리가 체계적이라는 장점이 있습니다", "시설이 아쉽다는 후기도 있습니다", "커리큘럼 정보가 공개되어 있습니다"])
            lines.append(f"- {b}: {tone}.")
        if not brands:
            lines.append("기숙학원은 관리 강도, 시설, 급식, 통학 거리 등을 비교해 고르는 것이 좋습니다.")
        srcs = rnd.sample(_SOURCES, rnd.randint(2, 5))
        cites = [Citation(u, t, "", rnd.random() < 0.6) for u, t in srcs]
        return EngineResult(self.name, self.model, "\n".join(lines), cites)
