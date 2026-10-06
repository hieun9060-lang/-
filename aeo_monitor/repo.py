"""모니터링 서비스용 DB 접근 (회사·채널·게시물·요약·보고서·질문·설정·작업)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import config
from .config import Brand, BrandConfig, Question
from .storage import Store
from .timeutil import now_kst

ROLES = ("ours", "competitor")
PLATFORMS = ("blog", "youtube", "homepage", "rss")


def _j(v, default):
    try:
        return json.loads(v) if isinstance(v, str) else (v if v is not None else default)
    except ValueError:
        return default


def slugify(name: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    h = hashlib.sha1(f"{name}{now_kst().timestamp()}".encode()).hexdigest()[:6]
    return f"{base[:20] + '_' if base else 'co_'}{h}"


class Repo:
    def __init__(self, store: Store):
        self.store = store
        self.conn = store.conn

    # ---------- kv / 설정 ----------
    def kv_get(self, key: str, default=None):
        r = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return _j(r["value"], default) if r else default

    def kv_set(self, key: str, value) -> None:
        self.conn.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, json.dumps(value, ensure_ascii=False)))
        self.conn.commit()

    def aeo_settings(self) -> dict:
        """AI 언급 측정 설정 (기존 settings.yaml 형식 + DB의 고정 질문)."""
        s = dict(self.kv_get("aeo", {}))
        s["panel_questions"] = [r["id"] for r in self.conn.execute(
            "SELECT id FROM questions WHERE panel=1 AND enabled=1 ORDER BY sort, id")]
        return s

    # ---------- 회사 ----------
    @staticmethod
    def _company(r) -> dict:
        d = dict(r)
        for k in ("aliases", "domains", "near", "near_exclude"):
            d[k] = _j(d.get(k), [])
        d["track_ai"] = bool(d["track_ai"])
        d["active"] = bool(d["active"])
        return d

    def companies(self, active_only: bool = True) -> list[dict]:
        q = "SELECT * FROM companies" + (" WHERE active=1" if active_only else "") + " ORDER BY role='ours' DESC, sort, name"
        return [self._company(r) for r in self.conn.execute(q)]

    def company(self, cid: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
        return self._company(r) if r else None

    def create_company(self, data: dict) -> str:
        cid = data.get("id") or slugify(data["name"])
        role = data.get("role", "competitor")
        if role == "ours":
            self.conn.execute("UPDATE companies SET role='competitor' WHERE role='ours'")  # 우리 회사는 하나
        n = self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        self.conn.execute(
            """INSERT INTO companies(id,name,role,color_idx,grp,template_name,aliases,domains,near,near_window,near_exclude,
               track_ai,active,sort,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, data["name"], role, data.get("color_idx", n % 8), data.get("grp", ""), data.get("template_name", ""),
             json.dumps(data.get("aliases", []), ensure_ascii=False), json.dumps(data.get("domains", []), ensure_ascii=False),
             json.dumps(data.get("near", []), ensure_ascii=False), data.get("near_window", 12),
             json.dumps(data.get("near_exclude", []), ensure_ascii=False), int(data.get("track_ai", True)), 1,
             data.get("sort", n), now_kst().isoformat(timespec="seconds")))
        self.conn.commit()
        return cid

    def update_company(self, cid: str, data: dict) -> None:
        cols = {"name": None, "role": None, "color_idx": None, "grp": None, "template_name": None, "near_window": None,
                "track_ai": int, "active": int, "sort": None}
        sets, vals = [], []
        for k, conv in cols.items():
            if k in data:
                sets.append(f"{k}=?")
                vals.append(conv(data[k]) if conv else data[k])
        for k in ("aliases", "domains", "near", "near_exclude"):
            if k in data:
                sets.append(f"{k}=?")
                vals.append(json.dumps(data[k], ensure_ascii=False))
        if data.get("role") == "ours":
            self.conn.execute("UPDATE companies SET role='competitor' WHERE role='ours' AND id<>?", (cid,))
        if sets:
            self.conn.execute(f"UPDATE companies SET {', '.join(sets)} WHERE id=?", (*vals, cid))
        self.conn.commit()

    def delete_company(self, cid: str) -> None:
        self.conn.execute("DELETE FROM posts WHERE company_id=?", (cid,))
        self.conn.execute("DELETE FROM channels WHERE company_id=?", (cid,))
        self.conn.execute("DELETE FROM day_summaries WHERE company_id=?", (cid,))
        self.conn.execute("DELETE FROM companies WHERE id=?", (cid,))
        self.conn.commit()

    def our_company(self) -> dict | None:
        r = self.conn.execute("SELECT * FROM companies WHERE role='ours' AND active=1 LIMIT 1").fetchone()
        return self._company(r) if r else None

    def brand_config(self) -> BrandConfig:
        """AI 언급 판정용 설정 (DB의 회사 목록 기준)."""
        brands: list[Brand] = []
        target = None
        for c in self.companies():
            if not c["track_ai"] and c["role"] != "ours":
                continue
            aliases = list(dict.fromkeys([*c["aliases"], c["name"], c["template_name"]]))
            brands.append(Brand(id=c["id"], name=c["name"], aliases=[a for a in aliases if a], template_name=c["template_name"] or c["name"],
                                group=c["grp"], near=c["near"], near_window=c["near_window"], near_exclude=c["near_exclude"],
                                domains=c["domains"]))
            if c["role"] == "ours":
                target = c["id"]
        grp = self.kv_get("target_group", {})
        return BrandConfig(target_id=target or (brands[0].id if brands else ""), brands=brands,
                           group_name=grp.get("name", ""), group_aliases=grp.get("aliases", []),
                           other_campus_words=grp.get("other_campus_words", []))

    # ---------- 채널 ----------
    def channels(self, company_id: str | None = None, active_only: bool = False) -> list[dict]:
        q, args = "SELECT * FROM channels WHERE 1=1", []
        if company_id:
            q += " AND company_id=?"
            args.append(company_id)
        if active_only:
            q += " AND active=1"
        q += " ORDER BY company_id, id"
        return [dict(r) | {"active": bool(r["active"])} for r in self.conn.execute(q, args)]

    def channel(self, chid: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM channels WHERE id=?", (chid,)).fetchone()
        return dict(r) | {"active": bool(r["active"])} if r else None

    def add_channel(self, company_id: str, type_: str, url: str, label: str = "") -> int:
        cur = self.conn.execute("INSERT INTO channels(company_id,type,url,label) VALUES (?,?,?,?)",
                                (company_id, type_, url, label))
        self.conn.commit()
        return cur.lastrowid

    def update_channel(self, chid: int, **fields) -> None:
        allowed = {"type", "url", "label", "active", "status", "status_msg", "feed_url", "last_checked_at",
                   "last_success_at", "item_count"}
        sets = [f"{k}=?" for k in fields if k in allowed]
        if sets:
            self.conn.execute(f"UPDATE channels SET {', '.join(sets)} WHERE id=?",
                              (*[v for k, v in fields.items() if k in allowed], chid))
            self.conn.commit()

    def delete_channel(self, chid: int) -> None:
        self.conn.execute("UPDATE posts SET channel_id=NULL WHERE channel_id=?", (chid,))
        self.conn.execute("DELETE FROM channels WHERE id=?", (chid,))
        self.conn.commit()

    # ---------- 게시물 ----------
    def upsert_post(self, *, company_id: str, channel_id: int | None, platform: str, url: str, title: str,
                    snippet: str, body: str, topic: str, published_at: str | None, post_date: str,
                    baseline: bool = False) -> bool:
        """새 게시물이면 True."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO posts(company_id,channel_id,platform,url,title,snippet,body,topic,published_at,post_date,
               first_seen_at,baseline) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (company_id, channel_id, platform, url, title[:300], snippet[:400], body[:4000], topic, published_at, post_date,
             now_kst().isoformat(timespec="seconds"), int(baseline)))
        return cur.rowcount > 0

    def known_urls(self, company_id: str) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT url FROM posts WHERE company_id=?", (company_id,))}

    def post_count(self, channel_id: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM posts WHERE channel_id=?", (channel_id,)).fetchone()[0]

    def posts(self, start: str, end: str, *, company_id: str | None = None, platform: str | None = None,
              topic: str | None = None, q: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
        sql = ("SELECT p.*, c.name AS company_name FROM posts p JOIN companies c ON c.id=p.company_id "
               "WHERE p.baseline=0 AND c.active=1 AND p.post_date BETWEEN ? AND ?")
        args: list[Any] = [start, end]
        for col, val in (("p.company_id", company_id), ("p.platform", platform), ("p.topic", topic)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        if q:
            sql += " AND (p.title LIKE ? OR p.snippet LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        sql += " ORDER BY p.post_date DESC, COALESCE(p.published_at, p.first_seen_at) DESC, p.id DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        return [dict(r) for r in self.conn.execute(sql, args)]

    def post_total(self, start: str, end: str, *, company_id=None, platform=None, topic=None, q=None) -> int:
        sql = ("SELECT COUNT(*) FROM posts p JOIN companies c ON c.id=p.company_id "
               "WHERE p.baseline=0 AND c.active=1 AND p.post_date BETWEEN ? AND ?")
        args: list[Any] = [start, end]
        for col, val in (("p.company_id", company_id), ("p.platform", platform), ("p.topic", topic)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        if q:
            sql += " AND (p.title LIKE ? OR p.snippet LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        return self.conn.execute(sql, args).fetchone()[0]

    def post_counts(self, start: str, end: str) -> list[dict]:
        """(날짜, 회사, 플랫폼, 주제)별 건수."""
        return [dict(r) for r in self.conn.execute(
            """SELECT p.post_date AS date, p.company_id, p.platform, p.topic, COUNT(*) AS n
               FROM posts p JOIN companies c ON c.id=p.company_id
               WHERE p.baseline=0 AND c.active=1 AND p.post_date BETWEEN ? AND ?
               GROUP BY p.post_date, p.company_id, p.platform, p.topic""", (start, end))]

    def post_topics(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT DISTINCT topic FROM posts WHERE baseline=0 ORDER BY topic")]

    # ---------- 요약 / 보고서 ----------
    def day_summaries(self, date: str) -> dict[str, dict]:
        return {r["company_id"]: dict(r) for r in self.conn.execute("SELECT * FROM day_summaries WHERE date=?", (date,))}

    def set_day_summary(self, date: str, company_id: str, issue: str, summary: str, highlight: str, model: str) -> None:
        self.conn.execute(
            """INSERT INTO day_summaries(date,company_id,issue,summary,highlight,model,created_at) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(date,company_id) DO UPDATE SET issue=excluded.issue, summary=excluded.summary,
               highlight=excluded.highlight, model=excluded.model, created_at=excluded.created_at""",
            (date, company_id, issue, summary, highlight, model, now_kst().isoformat(timespec="seconds")))
        self.conn.commit()

    def report(self, kind: str, period_start: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM analysis_reports WHERE kind=? AND period_start=?", (kind, period_start)).fetchone()
        return (dict(r) | {"payload": _j(r["payload"], {})}) if r else None

    def set_report(self, kind: str, start: str, end: str, payload: dict, model: str) -> None:
        self.conn.execute(
            """INSERT INTO analysis_reports(kind,period_start,period_end,payload,model,created_at) VALUES (?,?,?,?,?,?)
               ON CONFLICT(kind,period_start) DO UPDATE SET period_end=excluded.period_end, payload=excluded.payload,
               model=excluded.model, created_at=excluded.created_at""",
            (kind, start, end, json.dumps(payload, ensure_ascii=False), model, now_kst().isoformat(timespec="seconds")))
        self.conn.commit()

    # ---------- AI 질문 ----------
    def questions(self) -> list[dict]:
        out = []
        for r in self.conn.execute("SELECT * FROM questions ORDER BY sort, id"):
            d = dict(r)
            d["categories"] = _j(d["categories"], [])
            d["enabled"], d["panel"] = bool(d["enabled"]), bool(d["panel"])
            out.append(d)
        return out

    def upsert_question(self, q: dict) -> str:
        qid = q.get("id")
        if not qid:
            n = self.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            qid = f"u{now_kst().strftime('%y%m%d%H%M%S')}{n}"
        self.conn.execute(
            """INSERT INTO questions(id,text,categories,origin,views,source_url,enabled,panel,sort) VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET text=excluded.text, categories=excluded.categories, enabled=excluded.enabled,
               panel=excluded.panel""",
            (qid, q["text"], json.dumps(q.get("categories", []), ensure_ascii=False), q.get("origin", "custom"),
             q.get("views", 0), q.get("source_url", ""), int(q.get("enabled", True)), int(q.get("panel", False)),
             q.get("sort", 10_000)))
        self.conn.commit()
        return qid

    def delete_question(self, qid: str) -> None:
        self.conn.execute("DELETE FROM questions WHERE id=?", (qid,))
        self.conn.commit()

    def load_questions(self, brands: BrandConfig, include_templates: bool = True) -> list[Question]:
        out = [Question(id=r["id"], text=r["text"], categories=r["categories"], origin=r["origin"],
                        branded=config.is_branded(r["text"], brands), views=r["views"] or 0, source_url=r["source_url"] or "")
               for r in self.questions() if r["enabled"]]
        if include_templates:
            out += config.template_questions(brands)
        return out

    # ---------- AI 언급 일일 결과 ----------
    def save_aeo_day(self, run_date: str, demo: bool, payload: dict) -> None:
        self.conn.execute(
            """INSERT INTO aeo_days(run_date,demo,payload,generated_at) VALUES (?,?,?,?)
               ON CONFLICT(run_date,demo) DO UPDATE SET payload=excluded.payload, generated_at=excluded.generated_at""",
            (run_date, int(demo), json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
             now_kst().isoformat(timespec="seconds")))
        self.conn.commit()

    def aeo_day(self, run_date: str, demo: bool = False) -> dict | None:
        r = self.conn.execute("SELECT payload FROM aeo_days WHERE run_date=? AND demo=?", (run_date, int(demo))).fetchone()
        return _j(r["payload"], None) if r else None

    def aeo_days(self, demo: bool = False) -> list[dict]:
        out = []
        for r in self.conn.execute("SELECT run_date, payload FROM aeo_days WHERE demo=? ORDER BY run_date", (int(demo),)):
            p = _j(r["payload"], {})
            k = p.get("kpi", {})
            out.append({"date": r["run_date"], "todayRate": k.get("today_rate"), "windowRate": k.get("target_rate"),
                        "byEngine": {x["key"]: x["rate"] for x in p.get("byEngine", [])},
                        "officialRate": k.get("official_cited_rate"), "brandOnlyRate": k.get("brand_only_rate"),
                        "topAction": (p.get("actions") or [{}])[0].get("title", "")})
        return out

    # ---------- 작업 ----------
    def create_job(self, kind: str, trigger: str = "manual") -> int:
        cur = self.conn.execute("INSERT INTO jobs(kind,trigger,status,started_at) VALUES (?,?,?,?)",
                                (kind, trigger, "running", now_kst().isoformat(timespec="seconds")))
        self.conn.commit()
        return cur.lastrowid

    def update_job(self, jid: int, *, progress: str | None = None, status: str | None = None, result: dict | None = None) -> None:
        sets, vals = [], []
        if progress is not None:
            sets.append("progress=?")
            vals.append(progress)
        if status is not None:
            sets.append("status=?")
            vals.append(status)
            if status != "running":
                sets.append("finished_at=?")
                vals.append(now_kst().isoformat(timespec="seconds"))
        if result is not None:
            sets.append("result=?")
            vals.append(json.dumps(result, ensure_ascii=False))
        if sets:
            self.conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", (*vals, jid))
            self.conn.commit()

    def job(self, jid: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return (dict(r) | {"result": _j(r["result"], {})}) if r else None

    def latest_job(self) -> dict | None:
        r = self.conn.execute("SELECT id FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
        return self.job(r["id"]) if r else None

    def recent_jobs(self, n: int = 10) -> list[dict]:
        return [self.job(r["id"]) for r in self.conn.execute("SELECT id FROM jobs ORDER BY id DESC LIMIT ?", (n,))]

    def fail_stale_jobs(self) -> None:
        self.conn.execute("UPDATE jobs SET status='error', finished_at=?, progress='서버 재시작으로 중단됨' WHERE status='running'",
                          (now_kst().isoformat(timespec="seconds"),))
        self.conn.commit()
