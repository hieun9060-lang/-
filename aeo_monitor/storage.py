"""SQLite 저장소: 날짜별 측정 이력을 쌓아 추이를 본다."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT NOT NULL,          -- KST 기준 날짜 YYYY-MM-DD
  started_at TEXT NOT NULL,
  engines TEXT NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES runs(id),
  question_id TEXT NOT NULL,
  question TEXT NOT NULL,
  categories TEXT NOT NULL,        -- JSON list
  origin TEXT NOT NULL,
  branded INTEGER NOT NULL,
  brand_scope TEXT,
  template_id TEXT,
  engine TEXT NOT NULL,
  model TEXT,
  sample INTEGER NOT NULL DEFAULT 1,
  answer TEXT,
  error TEXT,
  group_only INTEGER DEFAULT 0,    -- 이투스247 브랜드만 언급(캠퍼스 불명)
  other_campus TEXT,               -- JSON list, 캠퍼스 혼동 신호
  panel INTEGER DEFAULT 0          -- 매일 고정 질문
);
CREATE TABLE IF NOT EXISTS mentions (
  response_id INTEGER NOT NULL REFERENCES responses(id),
  brand_id TEXT NOT NULL,
  mentioned INTEGER NOT NULL,
  rank INTEGER,
  count INTEGER,
  sentiment TEXT,
  snippet TEXT
);
CREATE TABLE IF NOT EXISTS citations (
  response_id INTEGER NOT NULL REFERENCES responses(id),
  url TEXT NOT NULL,
  domain TEXT,
  title TEXT,
  source_type TEXT,
  cited_in_answer INTEGER,
  mentions_target INTEGER          -- 출처 제목/인용문에 대상 학원이 나오는지
);
-- ===== 모니터링 서비스(회사·채널·게시물·설정·작업) =====
CREATE TABLE IF NOT EXISTS companies (
  id TEXT PRIMARY KEY,             -- slug (AI 언급 brand_id 와 동일)
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'competitor',   -- ours | competitor
  color_idx INTEGER NOT NULL DEFAULT 0,
  grp TEXT DEFAULT '',             -- 같은 계열(예: etoos) — 자사 계열 캠퍼스 구분용
  template_name TEXT DEFAULT '',
  aliases TEXT NOT NULL DEFAULT '[]',        -- JSON: AI 답변에서 이 학원으로 인정하는 표기
  domains TEXT NOT NULL DEFAULT '[]',        -- JSON: 공식 사이트 도메인 조각
  near TEXT NOT NULL DEFAULT '[]',           -- JSON: [[A,B],...] 근접 판정
  near_window INTEGER NOT NULL DEFAULT 12,
  near_exclude TEXT NOT NULL DEFAULT '[]',
  track_ai INTEGER NOT NULL DEFAULT 1,       -- AI 챗봇 언급 판정 대상
  active INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  type TEXT NOT NULL,              -- blog | youtube | homepage | rss
  url TEXT NOT NULL,
  label TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending',    -- pending | ok | warn | login | error
  status_msg TEXT DEFAULT '',
  feed_url TEXT DEFAULT '',        -- 해석된 RSS/Atom 주소
  last_checked_at TEXT,
  last_success_at TEXT,
  item_count INTEGER DEFAULT 0,
  UNIQUE(company_id, url)
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  channel_id INTEGER REFERENCES channels(id) ON DELETE SET NULL,
  platform TEXT NOT NULL,          -- blog | youtube | homepage | rss
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  snippet TEXT DEFAULT '',
  body TEXT DEFAULT '',            -- AI 요약용 본문(최대 4000자)
  topic TEXT DEFAULT '기타',
  published_at TEXT,               -- KST ISO. 알 수 없으면 NULL
  post_date TEXT NOT NULL,         -- 캘린더 기준일(YYYY-MM-DD) = 발행일, 없으면 수집일
  first_seen_at TEXT NOT NULL,
  baseline INTEGER NOT NULL DEFAULT 0,       -- 홈페이지 첫 수집분(새 글이 아님)
  UNIQUE(company_id, url)
);
CREATE INDEX IF NOT EXISTS ix_posts_date ON posts(post_date);
CREATE INDEX IF NOT EXISTS ix_posts_company ON posts(company_id, post_date);
CREATE TABLE IF NOT EXISTS day_summaries (
  date TEXT NOT NULL,
  company_id TEXT NOT NULL,
  issue TEXT DEFAULT '',
  summary TEXT DEFAULT '',
  highlight TEXT DEFAULT '',
  model TEXT DEFAULT '',
  created_at TEXT,
  PRIMARY KEY (date, company_id)
);
CREATE TABLE IF NOT EXISTS analysis_reports (
  kind TEXT NOT NULL,              -- week | month
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  payload TEXT NOT NULL,           -- JSON(통계 + AI 분석 텍스트)
  model TEXT DEFAULT '',
  created_at TEXT,
  PRIMARY KEY (kind, period_start)
);
CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  categories TEXT NOT NULL DEFAULT '[]',
  origin TEXT NOT NULL DEFAULT 'custom',
  views INTEGER DEFAULT 0,
  source_url TEXT DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  panel INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aeo_days (
  run_date TEXT NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0,
  payload TEXT NOT NULL,           -- 그날의 AI 언급 인사이트 전체(JSON)
  generated_at TEXT,
  PRIMARY KEY (run_date, demo)
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  trigger TEXT NOT NULL DEFAULT 'manual',
  status TEXT NOT NULL DEFAULT 'running',    -- running | done | error
  started_at TEXT NOT NULL,
  finished_at TEXT,
  progress TEXT DEFAULT '',
  result TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_resp_run ON responses(run_id);
CREATE INDEX IF NOT EXISTS ix_men_resp ON mentions(response_id);
CREATE INDEX IF NOT EXISTS ix_cit_resp ON citations(response_id);
"""


class Store:
    _initialized: set = set()  # 프로세스 안에서 스키마는 DB마다 한 번만 만든다

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not path.exists()
        self.conn = sqlite3.connect(path, timeout=30, check_same_thread=False)  # 요청마다 새 연결, 스레드 간 이동만 허용
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        key = str(path.resolve())
        if fresh or key not in Store._initialized:
            self.conn.executescript(SCHEMA)
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(responses)")}
            if "panel" not in cols:  # 이전 버전 DB
                self.conn.execute("ALTER TABLE responses ADD COLUMN panel INTEGER DEFAULT 0")
                self.conn.commit()
            Store._initialized.add(key)

    def close(self) -> None:
        self.conn.close()

    def new_run(self, run_date: str, started_at: str, engines: list[str], demo: bool) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(run_date, started_at, engines, demo) VALUES (?,?,?,?)",
            (run_date, started_at, json.dumps(engines), int(demo)),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_response(self, run_id: int, q, engine: str, model: str, sample: int, answer: str,
                     error: str, group_info: dict, mentions: dict, citations: list[dict]) -> int:
        cur = self.conn.execute(
            """INSERT INTO responses(run_id, question_id, question, categories, origin, branded, brand_scope,
               template_id, engine, model, sample, answer, error, group_only, other_campus, panel)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, q.id, q.text, json.dumps(q.categories, ensure_ascii=False), q.origin, int(q.branded),
             q.brand_scope, q.template_id, engine, model, sample, answer, error,
             int(group_info.get("brand_only", False)),
             json.dumps(group_info.get("other_campus", []), ensure_ascii=False), int(getattr(q, "panel", False))),
        )
        rid = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO mentions VALUES (?,?,?,?,?,?,?)",
            [(rid, m.brand_id, int(m.mentioned), m.rank, m.count, m.sentiment, m.snippet) for m in mentions.values()],
        )
        self.conn.executemany(
            "INSERT INTO citations VALUES (?,?,?,?,?,?,?)",
            [(rid, c["url"], c["domain"], c["title"], c["source_type"], int(c["cited_in_answer"]),
              int(c["mentions_target"])) for c in citations],
        )
        self.conn.commit()
        return rid

    # ---- 조회 ----
    def latest_run(self, run_date: str | None = None) -> sqlite3.Row | None:
        if run_date:
            return self.conn.execute(
                "SELECT * FROM runs WHERE run_date=? ORDER BY id DESC LIMIT 1", (run_date,)).fetchone()
        return self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()

    def previous_run(self, run: sqlite3.Row) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM runs WHERE run_date < ? AND demo = ? ORDER BY run_date DESC, id DESC LIMIT 1",
            (run["run_date"], run["demo"]),
        ).fetchone()

    def runs_between(self, start: str, end: str, demo: int) -> list[sqlite3.Row]:
        """각 날짜의 마지막 실행만."""
        return self.conn.execute(
            """SELECT * FROM runs WHERE id IN (
                 SELECT MAX(id) FROM runs WHERE run_date BETWEEN ? AND ? AND demo = ? GROUP BY run_date)
               ORDER BY run_date""",
            (start, end, demo),
        ).fetchall()

    def window_response_ids(self, start: str, end: str, demo: int) -> list[int]:
        """기간 내 (질문, 엔진)별 가장 최근 정상 답변. 오늘 오류가 났으면 그 전 정상 답변을 사용."""
        rows = self.conn.execute(
            """SELECT r.id, r.question_id, r.engine, r.answer, r.error, ru.run_date
               FROM responses r JOIN runs ru ON ru.id = r.run_id
               WHERE ru.run_date BETWEEN ? AND ? AND ru.demo = ?
               ORDER BY ru.run_date DESC, r.id DESC""", (start, end, demo)).fetchall()
        best: dict[tuple, int] = {}
        fallback: dict[tuple, int] = {}
        for r in rows:
            key = (r["question_id"], r["engine"])
            if r["answer"] and key not in best:
                best[key] = r["id"]
            fallback.setdefault(key, r["id"])
        return sorted({**fallback, **best}.values())

    def responses_by_ids(self, ids: list[int]) -> list[sqlite3.Row]:
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        return self.conn.execute(f"SELECT * FROM responses WHERE id IN ({q}) ORDER BY id", ids).fetchall()

    def mentions_by_ids(self, ids: list[int]) -> list[sqlite3.Row]:
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        return self.conn.execute(f"SELECT * FROM mentions WHERE response_id IN ({q})", ids).fetchall()

    def citations_by_ids(self, ids: list[int]) -> list[sqlite3.Row]:
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        return self.conn.execute(f"SELECT * FROM citations WHERE response_id IN ({q})", ids).fetchall()

    def responses(self, run_id: int) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM responses WHERE run_id=? ORDER BY id", (run_id,)).fetchall()

    def mentions(self, run_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT m.* FROM mentions m JOIN responses r ON r.id=m.response_id WHERE r.run_id=?", (run_id,)
        ).fetchall()

    def citations(self, run_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT c.* FROM citations c JOIN responses r ON r.id=c.response_id WHERE r.run_id=?", (run_id,)
        ).fetchall()
