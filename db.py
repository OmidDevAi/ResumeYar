import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("RESUMEYAR_DATA", BASE_DIR / "data")).resolve()
DB_PATH = DATA_DIR / "resumeyar.db"
UPLOADS_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
SECRET_PATH = DATA_DIR / "secret.key"

DEFAULT_SETTINGS = {
    "ai_enabled": "0",
    "ai_base_url": "https://api.openai.com/v1",
    "ai_api_key": "",
    "ai_model": "gpt-4o-mini",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_security": "starttls",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from_name": "",
    "smtp_from_email": "",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs():
    for path in (DATA_DIR, UPLOADS_DIR, GENERATED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def connect():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    full_name TEXT NOT NULL DEFAULT '',
    headline TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    links TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    skills TEXT NOT NULL DEFAULT '',
    languages TEXT NOT NULL DEFAULT '',
    experiences TEXT NOT NULL DEFAULT '[]',
    education TEXT NOT NULL DEFAULT '[]',
    preferences TEXT NOT NULL DEFAULT '{}',
    cv_text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'سایر',
    original_name TEXT NOT NULL DEFAULT '',
    stored_name TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'fa',
    work_mode TEXT NOT NULL DEFAULT '',
    employment_type TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    matched_skills TEXT NOT NULL DEFAULT '[]',
    missing_keywords TEXT NOT NULL DEFAULT '[]',
    match_notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    headline TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    skills TEXT NOT NULL DEFAULT '[]',
    cover_letter TEXT NOT NULL DEFAULT '',
    tailored_json TEXT NOT NULL DEFAULT '{}',
    cv_path TEXT NOT NULL DEFAULT '',
    cover_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    mode TEXT NOT NULL DEFAULT 'local',
    sent_at TEXT NOT NULL DEFAULT '',
    sent_to TEXT NOT NULL DEFAULT '',
    sent_subject TEXT NOT NULL DEFAULT '',
    sent_body TEXT NOT NULL DEFAULT '',
    sent_files TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_created ON applications(created_at DESC);
"""


def _migrate(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for name in ("work_mode", "employment_type"):
        if name not in columns:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def init_db():
    ensure_dirs()
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute(
            "INSERT OR IGNORE INTO profile (id, updated_at) VALUES (1, ?)",
            (now_iso(),),
        )
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()


def _json_load(value, fallback):
    try:
        parsed = json.loads(value) if value else fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def get_settings(conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        data = dict(DEFAULT_SETTINGS)
        data.update({row["key"]: row["value"] for row in rows})
        return data
    finally:
        if close:
            conn.close()


def save_settings(values, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        for key, value in values.items():
            if key not in DEFAULT_SETTINGS:
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value or "")),
            )
        conn.commit()
    finally:
        if close:
            conn.close()


def get_profile(conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        profile = dict(row) if row else {"id": 1}
        profile["experiences"] = _json_load(profile.get("experiences"), [])
        profile["education"] = _json_load(profile.get("education"), [])
        profile["preferences"] = _json_load(profile.get("preferences"), {})
        return profile
    finally:
        if close:
            conn.close()


PROFILE_FIELDS = (
    "full_name", "headline", "email", "phone", "city", "links", "summary",
    "skills", "languages", "experiences", "education", "preferences", "cv_text",
)


def save_profile(values, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        current = get_profile(conn)
        merged = {key: values.get(key, current.get(key, "")) for key in PROFILE_FIELDS}
        for key in ("experiences", "education", "preferences"):
            if not isinstance(merged[key], str):
                merged[key] = json.dumps(merged[key], ensure_ascii=False)
        conn.execute(
            """UPDATE profile SET full_name=?, headline=?, email=?, phone=?, city=?,
               links=?, summary=?, skills=?, languages=?, experiences=?, education=?,
               preferences=?, cv_text=?, updated_at=? WHERE id=1""",
            (
                merged["full_name"], merged["headline"], merged["email"], merged["phone"],
                merged["city"], merged["links"], merged["summary"], merged["skills"],
                merged["languages"], merged["experiences"], merged["education"],
                merged["preferences"], merged["cv_text"], now_iso(),
            ),
        )
        conn.commit()
        return get_profile(conn)
    finally:
        if close:
            conn.close()


def list_documents(conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC"
        ).fetchall()]
    finally:
        if close:
            conn.close()


def get_document(doc_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if close:
            conn.close()


def add_document(title, kind, original_name, stored_name, size, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        cur = conn.execute(
            "INSERT INTO documents (title, kind, original_name, stored_name, size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, kind, original_name, stored_name, size, now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close:
            conn.close()


def delete_document(doc_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT stored_name FROM documents WHERE id = ?", (doc_id,)).fetchone()
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        return row["stored_name"] if row else None
    finally:
        if close:
            conn.close()


def _job_row(row):
    job = dict(row)
    job["matched_skills"] = _json_load(job.get("matched_skills"), [])
    job["missing_keywords"] = _json_load(job.get("missing_keywords"), [])
    return job


def add_job(data, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        stamp = now_iso()
        cur = conn.execute(
            """INSERT INTO jobs (title, company, location, url, source, description,
               contact_email, language, work_mode, employment_type, score,
               matched_skills, missing_keywords, match_notes, status, notes,
               created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("title", "").strip() or "بدون عنوان",
                data.get("company", "").strip(),
                data.get("location", "").strip(),
                data.get("url", "").strip(),
                data.get("source", "").strip(),
                data.get("description", "").strip(),
                data.get("contact_email", "").strip(),
                data.get("language", "fa"),
                data.get("work_mode", ""),
                data.get("employment_type", ""),
                int(data.get("score", 0) or 0),
                json.dumps(data.get("matched_skills", []), ensure_ascii=False),
                json.dumps(data.get("missing_keywords", []), ensure_ascii=False),
                data.get("match_notes", ""),
                data.get("status", "new"),
                data.get("notes", "").strip(),
                stamp,
                stamp,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close:
            conn.close()


def update_job(job_id, values, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        allowed = {
            "title", "company", "location", "url", "source", "description",
            "contact_email", "language", "work_mode", "employment_type",
            "score", "match_notes", "status", "notes",
        }
        fields, params = [], []
        for key, value in values.items():
            if key in allowed:
                fields.append(f"{key} = ?")
                params.append(value)
        for key in ("matched_skills", "missing_keywords"):
            if key in values:
                fields.append(f"{key} = ?")
                params.append(json.dumps(values[key], ensure_ascii=False))
        if not fields:
            return
        fields.append("updated_at = ?")
        params.extend([now_iso(), job_id])
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    finally:
        if close:
            conn.close()


def get_job(job_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_row(row) if row else None
    finally:
        if close:
            conn.close()


def list_jobs(status="", query="", work_mode="", employment_type="", limit=200, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        sql = (
            "SELECT j.*, a.id AS application_id, a.status AS application_status "
            "FROM jobs j LEFT JOIN applications a ON a.job_id = j.id"
        )
        where, params = [], []
        if status:
            where.append("j.status = ?")
            params.append(status)
        if work_mode:
            where.append("j.work_mode = ?")
            params.append(work_mode)
        if employment_type:
            where.append("j.employment_type = ?")
            params.append(employment_type)
        if query:
            where.append("(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)")
            needle = f"%{query}%"
            params.extend([needle, needle, needle])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY j.created_at DESC LIMIT ?"
        params.append(limit)
        return [_job_row(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        if close:
            conn.close()


def delete_job(job_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        if close:
            conn.close()


def job_url_exists(url, conn=None):
    return get_job_by_url(url, conn) is not None


def get_job_by_url(url, conn=None):
    if not url:
        return None
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE url = ? LIMIT 1", (url,)).fetchone()
        return _job_row(row) if row else None
    finally:
        if close:
            conn.close()


def get_application(app_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT a.*, j.title AS job_title, j.company AS job_company, j.location AS job_location, "
            "j.url AS job_url, j.source AS job_source, j.description AS job_description, "
            "j.contact_email AS job_contact_email, j.language AS job_language, "
            "j.score AS job_score, j.matched_skills AS job_matched_skills, "
            "j.missing_keywords AS job_missing_keywords, j.status AS job_status "
            "FROM applications a JOIN jobs j ON j.id = a.job_id WHERE a.id = ?",
            (app_id,),
        ).fetchone()
        if not row:
            return None
        app = dict(row)
        app["skills_list"] = _json_load(app.get("skills"), [])
        app["tailored"] = _json_load(app.get("tailored_json"), {})
        app["sent_files"] = _json_load(app.get("sent_files"), [])
        app["job_matched_skills"] = _json_load(app.get("job_matched_skills"), [])
        app["job_missing_keywords"] = _json_load(app.get("job_missing_keywords"), [])
        return app
    finally:
        if close:
            conn.close()


def get_application_by_job(job_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT id FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        return get_application(row["id"], conn) if row else None
    finally:
        if close:
            conn.close()


def create_application(job_id, values, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        stamp = now_iso()
        cur = conn.execute(
            """INSERT INTO applications (job_id, headline, summary, skills, cover_letter,
               tailored_json, cv_path, cover_path, status, mode, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                values.get("headline", ""),
                values.get("summary", ""),
                json.dumps(values.get("skills", []), ensure_ascii=False),
                values.get("cover_letter", ""),
                json.dumps(values.get("tailored", {}), ensure_ascii=False),
                values.get("cv_path", ""),
                values.get("cover_path", ""),
                values.get("status", "draft"),
                values.get("mode", "local"),
                stamp,
                stamp,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close:
            conn.close()


def update_application(app_id, values, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        allowed = {
            "headline", "summary", "cover_letter", "cv_path", "cover_path",
            "status", "mode", "sent_at", "sent_to", "sent_subject", "sent_body",
        }
        fields, params = [], []
        for key, value in values.items():
            if key in allowed:
                fields.append(f"{key} = ?")
                params.append(value)
        for key, source in (
            ("skills", "skills"),
            ("tailored", "tailored_json"),
            ("sent_files", "sent_files"),
        ):
            if source in values:
                fields.append(f"{key} = ?")
                params.append(json.dumps(values[source], ensure_ascii=False))
        if not fields:
            return
        fields.append("updated_at = ?")
        params.extend([now_iso(), app_id])
        conn.execute(f"UPDATE applications SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    finally:
        if close:
            conn.close()


def list_applications(status="", conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        sql = (
            "SELECT a.*, j.title AS job_title, j.company AS job_company, j.url AS job_url, "
            "j.score AS job_score, j.source AS job_source "
            "FROM applications a JOIN jobs j ON j.id = a.job_id"
        )
        params = []
        if status:
            sql += " WHERE a.status = ?"
            params.append(status)
        sql += " ORDER BY a.created_at DESC"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        for row in rows:
            row["sent_files"] = _json_load(row.get("sent_files"), [])
        return rows
    finally:
        if close:
            conn.close()


def delete_application(app_id, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT job_id FROM applications WHERE id = ?", (app_id,)).fetchone()
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        if row:
            conn.execute(
                "UPDATE jobs SET status = 'new', updated_at = ? WHERE id = ? AND status = 'preparing'",
                (now_iso(), row["job_id"]),
            )
        conn.commit()
    finally:
        if close:
            conn.close()


def counts(conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        def scalar(sql, params=()):
            return conn.execute(sql, params).fetchone()[0]

        return {
            "jobs": scalar("SELECT COUNT(*) FROM jobs"),
            "new_jobs": scalar("SELECT COUNT(*) FROM jobs WHERE status = 'new'"),
            "applications": scalar("SELECT COUNT(*) FROM applications"),
            "sent": scalar("SELECT COUNT(*) FROM applications WHERE status = 'sent'"),
            "documents": scalar("SELECT COUNT(*) FROM documents"),
            "drafts": scalar("SELECT COUNT(*) FROM applications WHERE status != 'sent'"),
        }
    finally:
        if close:
            conn.close()


def recent_jobs(limit=5, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        return [_job_row(r) for r in conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]
    finally:
        if close:
            conn.close()


def recent_applications(limit=6, conn=None):
    close = conn is None
    conn = conn or connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT a.*, j.title AS job_title, j.company AS job_company "
            "FROM applications a JOIN jobs j ON j.id = a.job_id "
            "ORDER BY a.updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()]
    finally:
        if close:
            conn.close()
