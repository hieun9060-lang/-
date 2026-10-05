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
  other_campus TEXT                -- JSON list, 캠퍼스 혼동 신호
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
CREATE INDEX IF NOT EXISTS ix_resp_run ON responses(run_id);
CREATE INDEX IF NOT EXISTS ix_men_resp ON mentions(response_id);
CREATE INDEX IF NOT EXISTS ix_cit_resp ON citations(response_id);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

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
               template_id, engine, model, sample, answer, error, group_only, other_campus)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, q.id, q.text, json.dumps(q.categories, ensure_ascii=False), q.origin, int(q.branded),
             q.brand_scope, q.template_id, engine, model, sample, answer, error,
             int(group_info.get("brand_only", False)),
             json.dumps(group_info.get("other_campus", []), ensure_ascii=False)),
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
