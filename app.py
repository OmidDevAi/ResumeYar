import hmac
import io
import json
import os
import re
import secrets
import shutil
import threading
import uuid
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template, request,
    send_file, session, url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge

import db
from services import ai, cv_parse, emailer, jobsource, pdfgen, tailoring
from utils import (
    EMPLOYMENT_TYPES, WORK_MODES, analyze_match, build_search_links, detect_language,
    fa_digits, format_jalali, human_size, profile_completeness, split_list,
    summarize_job_text, truncate,
)

BASE_DIR = Path(os.environ.get("RESUMEYAR_ROOT") or Path(__file__).resolve().parent)
ALLOWED_CV_EXT = {".pdf", ".docx", ".txt"}
ALLOWED_DOC_EXT = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt"}
MAX_DOC_MB = 20
JOB_STATUSES = {
    "new": "جدید",
    "reviewing": "در حال بررسی",
    "preparing": "در حال آماده‌سازی",
    "applied": "ارسال‌شده",
    "archived": "بایگانی",
}
APP_STATUSES = {"draft": "آماده ارسال", "sent": "ارسال‌شده"}
SOURCE_OPTIONS = {
    key: {"name": value[0], "note": value[2]}
    for key, value in jobsource.SOURCES.items()
}


def _load_secret():
    db.ensure_dirs()
    if db.SECRET_PATH.exists():
        return db.SECRET_PATH.read_text(encoding="utf-8").strip()
    value = secrets.token_hex(32)
    db.SECRET_PATH.write_text(value, encoding="utf-8")
    try:
        os.chmod(db.SECRET_PATH, 0o600)
    except OSError:
        pass
    return value


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_load_secret(),
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
)
db.init_db()


# ---------- helpers ----------

def _csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = _csrf_token
app.jinja_env.filters.update({
    "jdate": lambda value: format_jalali(value),
    "jdatetime": lambda value: format_jalali(value, with_time=True),
    "fadigits": fa_digits,
    "filesize": human_size,
    "shorten": truncate,
})
app.jinja_env.globals["JOB_STATUSES"] = JOB_STATUSES
app.jinja_env.globals["APP_STATUSES"] = APP_STATUSES
app.jinja_env.globals["WORK_MODES"] = WORK_MODES
app.jinja_env.globals["EMPLOYMENT_TYPES"] = EMPLOYMENT_TYPES


def _load_globals():
    if not hasattr(g, "profile"):
        g.profile = db.get_profile()
        g.settings = db.get_settings()
        g.counts = db.counts()
    return g.profile, g.settings


@app.before_request
def _prepare():
    _load_globals()
    _csrf_token()
    if request.method == "POST":
        supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            abort(400, description="نشست شما منقضی شده است. صفحه را دوباره باز کنید.")


@app.context_processor
def _inject():
    profile, settings = _load_globals()
    completeness = profile_completeness(profile, g.counts["documents"])
    return {
        "profile": profile,
        "settings": settings,
        "counts": g.counts,
        "completeness": completeness,
        "smtp_ready": emailer.smtp_ready(settings),
        "ai_ready": ai.ai_ready(settings),
        "current_endpoint": request.endpoint or "",
    }


def _parse_json_list(raw, limit=15):
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return data[:limit] if isinstance(data, list) else []


def _clean_experiences(raw):
    result = []
    for item in _parse_json_list(raw, 15):
        if not isinstance(item, dict):
            continue
        bullets = item.get("bullets", [])
        if isinstance(bullets, str):
            bullets = bullets.split("\n")
        if not isinstance(bullets, list):
            bullets = []
        entry = {
            "title": str(item.get("title", "")).strip()[:200],
            "company": str(item.get("company", "")).strip()[:200],
            "location": str(item.get("location", "")).strip()[:120],
            "start": str(item.get("start", "")).strip()[:40],
            "end": str(item.get("end", "")).strip()[:40],
            "bullets": [str(b).strip()[:800] for b in bullets if str(b).strip()][:12],
        }
        if entry["title"] or entry["company"]:
            result.append(entry)
    return result


def _clean_education(raw):
    result = []
    for item in _parse_json_list(raw, 10):
        if not isinstance(item, dict):
            continue
        entry = {
            "degree": str(item.get("degree", "")).strip()[:150],
            "field": str(item.get("field", "")).strip()[:150],
            "school": str(item.get("school", "")).strip()[:220],
            "start": str(item.get("start", "")).strip()[:40],
            "end": str(item.get("end", "")).strip()[:40],
        }
        if entry["degree"] or entry["school"]:
            result.append(entry)
    return result


def _rescore_jobs():
    profile = db.get_profile()
    for job in db.list_jobs(limit=5000):
        match = analyze_match(profile, job)
        db.update_job(job["id"], match)


def _store_upload(file_storage, allowed_ext, max_mb=MAX_DOC_MB):
    original = file_storage.filename or ""
    ext = Path(original).suffix.lower()
    if ext not in allowed_ext:
        raise ValueError("فرمت فایل مجاز نیست.")
    stored = f"{uuid.uuid4().hex}{ext}"
    target = db.UPLOADS_DIR / stored
    file_storage.save(target)
    size = target.stat().st_size
    if size > max_mb * 1024 * 1024:
        target.unlink(missing_ok=True)
        raise ValueError(f"حجم فایل بیشتر از {max_mb} مگابایت است.")
    return stored, size


def _rel_data_path(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(db.DATA_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return ""


def _abs_data_path(relative):
    if not relative:
        return None
    path = (db.DATA_DIR / relative).resolve()
    try:
        path.relative_to(db.DATA_DIR.resolve())
    except ValueError:
        return None
    return path


def _send_pdf(relative_path, download=False, download_name=None):
    path = _abs_data_path(relative_path)
    if not path or not path.is_file():
        abort(404)
    return send_file(
        path, mimetype="application/pdf", as_attachment=download,
        download_name=download_name or path.name,
    )


def _job_dict_from_app(application):
    return {
        "id": application["job_id"],
        "title": application["job_title"],
        "company": application["job_company"],
        "location": application["job_location"],
        "url": application["job_url"],
        "source": application["job_source"],
        "description": application["job_description"],
        "contact_email": application["job_contact_email"],
        "language": application["job_language"],
        "score": application["job_score"],
    }


def _application_language(application):
    return "fa" if application.get("job_language") == "fa" else "en"


def _build_application_pdfs(job, application_id, profile, tailored, language):
    folder = db.GENERATED_DIR / f"job-{job['id']}"
    folder.mkdir(parents=True, exist_ok=True)
    cv_path = folder / "CV.pdf"
    cover_path = folder / "Cover-Letter.pdf"
    pdfgen.build_cv_pdf(cv_path, profile, tailored, language, job)
    pdfgen.build_cover_pdf(cover_path, profile, job, tailored.get("cover_letter", ""), language)
    return _rel_data_path(cv_path), _rel_data_path(cover_path)


def _generate_for_job(job, profile, language, mode):
    warnings = []
    existing = db.get_application_by_job(job["id"])
    if existing and existing["status"] == "sent":
        raise ValueError("این درخواست قبلاً ارسال شده و قابل بازتولید نیست.")
    use_ai = mode == "ai" or (mode == "auto" and ai.ai_ready(g.settings))
    tailored = None
    if use_ai:
        try:
            tailored = ai.tailor(profile, job, language, g.settings)
        except ai.AIError as exc:
            warnings.append(f"هوش مصنوعی پاسخ نداد؛ نسخه محلی ساخته شد. ({exc})")
    if tailored is None:
        tailored = tailoring.local_tailor(profile, job, language)

    if existing:
        application_id = existing["id"]
        db.update_application(application_id, {
            "headline": tailored["headline"],
            "summary": tailored["summary"],
            "skills": tailored["skills"],
            "cover_letter": tailored["cover_letter"],
            "tailored": tailored,
            "mode": tailored.get("mode", "local"),
            "status": "draft",
        })
    else:
        application_id = db.create_application(job["id"], {
            "headline": tailored["headline"],
            "summary": tailored["summary"],
            "skills": tailored["skills"],
            "cover_letter": tailored["cover_letter"],
            "tailored": tailored,
            "mode": tailored.get("mode", "local"),
            "status": "draft",
        })

    cv_rel, cover_rel = _build_application_pdfs(job, application_id, profile, tailored, language)
    db.update_application(application_id, {"cv_path": cv_rel, "cover_path": cover_rel})
    db.update_job(job["id"], {"status": "preparing", "language": language})
    return application_id, warnings, tailored


def _compose_defaults(application):
    profile = db.get_profile()
    job = _job_dict_from_app(application)
    language = _application_language(application)
    draft = tailoring.email_draft(profile, job, language)
    if application["status"] == "sent":
        return {
            "to": application["sent_to"],
            "subject": application["sent_subject"],
            "body": application["sent_body"],
        }
    return {
        "to": application["job_contact_email"],
        "subject": draft["subject"],
        "body": draft["body"],
    }


def _documents_for_ids(ids):
    if not ids:
        return []
    selected = []
    for doc in db.list_documents():
        if str(doc["id"]) in ids:
            selected.append(doc)
    return selected


def _application_view(application_id, compose=None, error=None):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    compose = compose or _compose_defaults(application)
    return render_template(
        "application_detail.html",
        application=application,
        language=_application_language(application),
        documents=db.list_documents(),
        compose=compose,
        compose_error=error,
    )


# ---------- dashboard ----------

@app.get("/")
def dashboard():
    counts = db.counts()
    completeness = profile_completeness(g.profile, counts["documents"])
    recent_jobs = db.recent_jobs(4)
    recent_apps = db.recent_applications(5)
    steps = [
        {"label": "پروفایل را کامل کنید", "done": completeness["percent"] >= 70,
         "url": url_for("profile_page")},
        {"label": "رزومه و مدارک را بارگذاری کنید", "done": counts["documents"] > 0,
         "url": url_for("profile_page") + "#documents"},
        {"label": "اولین آگهی را اضافه کنید", "done": counts["jobs"] > 0,
         "url": url_for("jobs_page")},
        {"label": "نسخه اختصاصی بسازید و ارسال کنید", "done": counts["sent"] > 0,
         "url": url_for("applications_page")},
    ]
    return render_template(
        "dashboard.html", counts=counts, recent_jobs=recent_jobs,
        recent_apps=recent_apps, steps=steps,
    )


# ---------- profile & documents ----------

@app.get("/profile")
def profile_page():
    return render_template("profile.html", documents=db.list_documents())


@app.post("/profile")
def save_profile_route():
    preferences = {
        "titles": request.form.get("pref_titles", "").strip(),
        "locations": request.form.get("pref_locations", "").strip(),
        "keywords": request.form.get("pref_keywords", "").strip(),
        "work_modes": [m for m in request.form.getlist("work_modes") if m in WORK_MODES],
        "employment_types": [t for t in request.form.getlist("employment_types")
                             if t in EMPLOYMENT_TYPES],
    }
    db.save_profile({
        "full_name": request.form.get("full_name", "").strip()[:150],
        "headline": request.form.get("headline", "").strip()[:200],
        "email": request.form.get("email", "").strip()[:200],
        "phone": request.form.get("phone", "").strip()[:80],
        "city": request.form.get("city", "").strip()[:100],
        "links": request.form.get("links", "").strip()[:1000],
        "summary": request.form.get("summary", "").strip()[:4000],
        "skills": request.form.get("skills", "").strip()[:2000],
        "languages": request.form.get("languages", "").strip()[:500],
        "experiences": _clean_experiences(request.form.get("experiences_json", "[]")),
        "education": _clean_education(request.form.get("education_json", "[]")),
        "preferences": preferences,
    })
    _rescore_jobs()
    flash("پروفایل ذخیره شد و امتیاز آگهی‌ها دوباره محاسبه شد.", "success")
    return redirect(url_for("profile_page"))


@app.post("/profile/cv")
def upload_cv():
    file = request.files.get("cv_file")
    if not file or not file.filename:
        flash("فایلی انتخاب نشده است.", "error")
        return redirect(url_for("profile_page") + "#cv")
    try:
        stored, size = _store_upload(file, ALLOWED_CV_EXT)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("profile_page") + "#cv")
    original = file.filename
    title = request.form.get("cv_title", "").strip() or "رزومه اصلی"
    db.add_document(title[:150], "رزومه", original[:250], stored, size)
    path = db.UPLOADS_DIR / stored
    try:
        text = cv_parse.extract_text(path)
    except cv_parse.CVParserError as exc:
        flash(f"فایل ذخیره شد اما متن آن خوانده نشد: {exc}", "warning")
        return redirect(url_for("profile_page") + "#documents")

    ai_profile = None
    ai_error = ""
    used_ai = False
    if ai.ai_ready(g.settings):
        try:
            ai_profile = ai.extract_profile(text, g.settings)
            used_ai = True
        except ai.AIError as exc:
            ai_error = str(exc)

    payload = cv_parse.profile_payload_from_cv(text, ai_profile)
    current = db.get_profile()
    updates = {
        "cv_text": text[:30000],
        "full_name": payload.get("full_name") or current.get("full_name", ""),
        "headline": payload.get("headline") or current.get("headline", ""),
        "email": payload.get("email") or current.get("email", ""),
        "phone": payload.get("phone") or current.get("phone", ""),
        "city": payload.get("city") or current.get("city", ""),
        "links": payload.get("links") or current.get("links", ""),
        "summary": payload.get("summary") or current.get("summary", ""),
        "skills": payload.get("skills") or current.get("skills", ""),
        "languages": payload.get("languages") or current.get("languages", ""),
    }
    if payload.get("experiences"):
        updates["experiences"] = payload["experiences"]
    if payload.get("education"):
        updates["education"] = payload["education"]
    db.save_profile(updates)
    _rescore_jobs()
    if ai_error:
        flash(f"رزومه خوانده شد، اما استخراج هوشمند انجام نشد: {ai_error}", "warning")
    mode = "با هوش مصنوعی" if used_ai else "به‌صورت خودکار"
    flash(f"رزومه {mode} خوانده شد؛ اطلاعات را در فرم بازبینی و تکمیل کنید.", "success")
    return redirect(url_for("profile_page"))


@app.post("/documents")
def upload_document():
    file = request.files.get("document_file")
    if not file or not file.filename:
        flash("فایلی انتخاب نشده است.", "error")
        return redirect(url_for("profile_page") + "#documents")
    try:
        stored, size = _store_upload(file, ALLOWED_DOC_EXT)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("profile_page") + "#documents")
    title = request.form.get("doc_title", "").strip() or file.filename
    kind = request.form.get("doc_kind", "").strip() or "سایر"
    db.add_document(title[:150], kind[:80], file.filename[:250], stored, size)
    flash("مدرک به آرشیو اضافه شد.", "success")
    return redirect(url_for("profile_page") + "#documents")


@app.get("/documents/<int:document_id>/download")
def download_document(document_id):
    doc = db.get_document(document_id)
    if not doc:
        abort(404)
    path = db.UPLOADS_DIR / doc["stored_name"]
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=doc["original_name"] or path.name)


@app.post("/documents/<int:document_id>/delete")
def delete_document(document_id):
    stored = db.delete_document(document_id)
    if stored:
        (db.UPLOADS_DIR / stored).unlink(missing_ok=True)
        flash("مدرک حذف شد.", "success")
    return redirect(url_for("profile_page") + "#documents")


# ---------- jobs ----------

@app.get("/jobs")
def jobs_page():
    status = request.args.get("status", "")
    query = request.args.get("q", "").strip()
    work_mode = request.args.get("mode", "")
    work_mode = work_mode if work_mode in WORK_MODES else ""
    employment_type = request.args.get("type", "")
    employment_type = employment_type if employment_type in EMPLOYMENT_TYPES else ""
    jobs = db.list_jobs(
        status=status if status in JOB_STATUSES else "", query=query,
        work_mode=work_mode, employment_type=employment_type,
    )
    prefs = g.profile.get("preferences", {}) or {}
    search_query = query or prefs.get("titles", "")
    location = prefs.get("locations", "")
    return render_template(
        "jobs.html", jobs=jobs, status=status, query=query,
        work_mode=work_mode, employment_type=employment_type, prefs=prefs,
        search_links=build_search_links(
            search_query, location, prefs.get("work_modes", []),
            prefs.get("employment_types", []),
        ),
        sources=SOURCE_OPTIONS, counts=db.counts(),
    )


@app.post("/jobs/import")
def import_job():
    url = request.form.get("url", "").strip()
    title = request.form.get("title", "").strip()
    company = request.form.get("company", "").strip()
    location = request.form.get("location", "").strip()
    description = request.form.get("description", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    language_choice = request.form.get("language", "auto")
    notes = request.form.get("notes", "").strip()
    source = request.form.get("source", "").strip()
    work_mode = request.form.get("work_mode", "").strip()
    work_mode = work_mode if work_mode in WORK_MODES else ""
    employment_type = request.form.get("employment_type", "").strip()
    employment_type = employment_type if employment_type in EMPLOYMENT_TYPES else ""
    warnings = []

    fetched = None
    if url and (not description or not title):
        try:
            fetched = jobsource.fetch_job_from_url(url)
        except jobsource.JobSourceError as exc:
            warnings.append(str(exc))
            if not title:
                flash(str(exc), "error")
                return redirect(url_for("jobs_page") + "#import")
    if fetched:
        title = title or fetched.get("title", "")
        company = company or fetched.get("company", "")
        location = location or fetched.get("location", "")
        description = description or fetched.get("description", "")
        contact_email = contact_email or fetched.get("contact_email", "")
        source = source or fetched.get("source", "")
    if not title or len(description) < 20:
        flash("عنوان و متن آگهی لازم است. متن آگهی را کامل‌تر وارد کنید.", "error")
        return redirect(url_for("jobs_page") + "#import")

    if url:
        existing = db.get_job_by_url(url)
        if existing:
            flash("این آگهی قبلاً ذخیره شده است.", "info")
            return redirect(url_for("job_detail", job_id=existing["id"]))

    language = language_choice if language_choice in ("fa", "en") else detect_language(title + " " + description)
    source = source or ("ورود دستی" if not url else re.sub(r"^www\.", "", url.split("/")[2]) if "//" in url else "ورود دستی")
    job_data = {
        "title": title[:300], "company": company[:200], "location": location[:150],
        "url": url[:1000], "source": source[:100], "description": summarize_job_text(description, 20000),
        "contact_email": contact_email[:250], "language": language, "notes": notes[:2000],
        "work_mode": work_mode, "employment_type": employment_type,
    }
    job_data.update(analyze_match(g.profile, job_data))
    job_id = db.add_job(job_data)
    if warnings:
        for warning in warnings:
            flash(warning, "warning")
    flash("آگهی ذخیره و امتیاز تطبیق محاسبه شد.", "success")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/jobs/discover")
def discover_jobs():
    source = request.form.get("source", "remoteok")
    query = request.form.get("discover_query", "").strip()
    work_mode = request.form.get("work_mode", "")
    work_mode = work_mode if work_mode in WORK_MODES else ""
    try:
        limit = max(3, min(20, int(request.form.get("limit", "8"))))
    except ValueError:
        limit = 8
    try:
        found = jobsource.discover(source, query, g.profile, limit=limit, work_mode=work_mode)
    except jobsource.JobSourceError as exc:
        flash(str(exc), "error")
        return redirect(url_for("jobs_page") + "#discover")
    added, skipped = 0, 0
    for item in found:
        if item.get("url") and db.job_url_exists(item["url"]):
            skipped += 1
            continue
        db.add_job(item)
        added += 1
    if added:
        flash(f"{fa_digits(added)} آگهی جدید از {SOURCE_OPTIONS.get(source, {}).get('name', source)} اضافه شد.", "success")
    elif skipped:
        flash("آگهی‌های یافت‌شده از قبل در آرشیو وجود داشتند.", "info")
    elif work_mode:
        flash(
            f"آگهی با شیوه همکاری «{WORK_MODES[work_mode]}» در این منبع پیدا نشد؛ "
            "همه منابع فعلی بیشتر ریموت هستند. فیلتر را بردارید یا از جستجوی سایت‌ها استفاده کنید.",
            "info",
        )
    else:
        flash("آگهی مرتبطی پیدا نشد؛ کلیدواژه انگلیسی یا منبع دیگری را امتحان کنید.", "info")
    return redirect(url_for("jobs_page"))


@app.post("/jobs/recalculate")
def recalculate_jobs():
    _rescore_jobs()
    flash("امتیاز همه آگهی‌ها بر اساس پروفایل فعلی بازمحاسبه شد.", "success")
    return redirect(url_for("jobs_page"))


@app.get("/jobs/<int:job_id>")
def job_detail(job_id):
    job = db.get_job(job_id)
    if not job:
        abort(404)
    application = db.get_application_by_job(job_id)
    search_query = job["title"]
    prefs = g.profile.get("preferences", {}) or {}
    return render_template(
        "job_detail.html", job=job, application=application,
        search_links=build_search_links(
            search_query, job.get("location", ""), prefs.get("work_modes", []),
            prefs.get("employment_types", []),
        ),
        language=job.get("language") if job.get("language") in ("fa", "en") else "fa",
    )


@app.post("/jobs/<int:job_id>/generate")
def generate_application(job_id):
    job = db.get_job(job_id)
    if not job:
        abort(404)
    profile = db.get_profile()
    if not profile.get("full_name") or not (profile.get("skills") or profile.get("experiences")):
        flash("برای ساخت رزومه اختصاصی، ابتدا نام و مهارت‌ها یا تجربه‌های خود را در پروفایل تکمیل کنید.", "error")
        return redirect(url_for("profile_page"))
    language = request.form.get("language", job.get("language", "fa"))
    language = language if language in ("fa", "en") else "fa"
    mode = request.form.get("mode", "auto")
    mode = mode if mode in ("auto", "ai", "local") else "auto"
    try:
        application_id, warnings, tailored = _generate_for_job(job, profile, language, mode)
    except (ValueError, ai.AIError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("job_detail", job_id=job_id))
    except Exception as exc:
        app.logger.exception("PDF generation failed")
        flash(f"ساخت فایل‌ها ناموفق بود: {exc}", "error")
        return redirect(url_for("job_detail", job_id=job_id))
    for warning in warnings:
        flash(warning, "warning")
    label = "با هوش مصنوعی" if tailored.get("mode") == "ai" else "با موتور محلی"
    flash(f"نسخه اختصاصی {label} ساخته شد. متن‌ها را بازبینی کنید و سپس ارسال کنید.", "success")
    return redirect(url_for("application_detail", application_id=application_id))


@app.post("/jobs/<int:job_id>/status")
def update_job_status(job_id):
    job = db.get_job(job_id)
    if not job:
        abort(404)
    status = request.form.get("status", "")
    if status in JOB_STATUSES:
        db.update_job(job_id, {"status": status})
        flash("وضعیت آگهی به‌روزرسانی شد.", "success")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/jobs/<int:job_id>/notes")
def update_job_notes(job_id):
    job = db.get_job(job_id)
    if not job:
        abort(404)
    db.update_job(job_id, {"notes": request.form.get("notes", "").strip()[:4000]})
    flash("یادداشت ذخیره شد.", "success")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/jobs/<int:job_id>/delete")
def delete_job_route(job_id):
    job = db.get_job(job_id)
    if not job:
        abort(404)
    db.delete_job(job_id)
    folder = db.GENERATED_DIR / f"job-{job_id}"
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    flash("آگهی و درخواست مرتبط حذف شد.", "success")
    return redirect(url_for("jobs_page"))


# ---------- applications ----------

@app.get("/applications")
def applications_page():
    status = request.args.get("status", "")
    applications = db.list_applications(status if status in APP_STATUSES else "")
    return render_template(
        "applications.html", applications=applications, status=status,
        counts=db.counts(),
    )


@app.get("/applications/<int:application_id>")
def application_detail(application_id):
    return _application_view(application_id)


@app.post("/applications/<int:application_id>/save")
def save_application(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    if application["status"] == "sent":
        flash("این درخواست ارسال شده و قابل ویرایش نیست.", "error")
        return redirect(url_for("application_detail", application_id=application_id))
    skills = split_list(request.form.get("skills", ""))[:40]
    headline = request.form.get("headline", "").strip()[:200]
    summary = request.form.get("summary", "").strip()[:2500]
    cover_letter = request.form.get("cover_letter", "").strip()[:12000]
    tailored = dict(application.get("tailored") or {})
    tailored.update({"headline": headline, "summary": summary, "skills": skills,
                     "cover_letter": cover_letter})
    profile = db.get_profile()
    job = _job_dict_from_app(application)
    language = _application_language(application)
    try:
        cv_rel, cover_rel = _build_application_pdfs(job, application_id, profile, tailored, language)
    except Exception as exc:
        app.logger.exception("PDF rebuild failed")
        flash(f"ذخیره شد اما ساخت PDF ناموفق بود: {exc}", "error")
        return redirect(url_for("application_detail", application_id=application_id))
    db.update_application(application_id, {
        "headline": headline, "summary": summary, "skills": skills,
        "cover_letter": cover_letter, "tailored": tailored,
        "cv_path": cv_rel, "cover_path": cover_rel,
    })
    flash("پیش‌نویس و فایل‌های PDF به‌روزرسانی شدند.", "success")
    return redirect(url_for("application_detail", application_id=application_id))


@app.post("/applications/<int:application_id>/regenerate")
def regenerate_application(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    if application["status"] == "sent":
        flash("این درخواست ارسال شده و قابل بازتولید نیست.", "error")
        return redirect(url_for("application_detail", application_id=application_id))
    job = _job_dict_from_app(application)
    profile = db.get_profile()
    language = request.form.get("language", application.get("job_language", "fa"))
    language = language if language in ("fa", "en") else "fa"
    mode = request.form.get("mode", "auto")
    mode = mode if mode in ("auto", "ai", "local") else "auto"
    try:
        _, warnings, tailored = _generate_for_job(job, profile, language, mode)
    except Exception as exc:
        app.logger.exception("Regeneration failed")
        flash(f"بازتولید ناموفق بود: {exc}", "error")
        return redirect(url_for("application_detail", application_id=application_id))
    for warning in warnings:
        flash(warning, "warning")
    flash("نسخه جدید ساخته شد؛ متن‌های قبلی جایگزین شدند.", "success")
    return redirect(url_for("application_detail", application_id=application_id))


@app.get("/applications/<int:application_id>/cv")
def application_cv(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    return _send_pdf(application["cv_path"], download=request.args.get("download") == "1",
                     download_name="CV.pdf")


@app.get("/applications/<int:application_id>/cover")
def application_cover(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    return _send_pdf(application["cover_path"], download=request.args.get("download") == "1",
                     download_name="Cover-Letter.pdf")


def _job_details_text(application, profile):
    job = _job_dict_from_app(application)
    lines = [
        "مشخصات آگهی",
        "=" * 30,
        f"عنوان: {job['title']}",
        f"شرکت: {job['company'] or '—'}",
        f"موقعیت: {job['location'] or '—'}",
        f"منبع: {job['source'] or '—'}",
        f"لینک: {job['url'] or '—'}",
        f"ایمیل تماس: {job['contact_email'] or '—'}",
        f"امتیاز تطبیق: {fa_digits(job['score'])} از ۱۰۰",
        f"تاریخ ثبت: {format_jalali(application['created_at'])}",
        "",
        "مهارت‌های مشترک:",
        "، ".join(application.get("job_matched_skills") or []) or "—",
        "",
        "کلیدواژه‌های قابل تقویت:",
        "، ".join(application.get("job_missing_keywords") or []) or "—",
        "",
        "شرح آگهی:",
        job["description"][:8000],
        "",
        "—" * 30,
        f"متقاضی: {profile.get('full_name', '')}",
    ]
    return "\n".join(lines)


@app.post("/applications/<int:application_id>/package")
def application_package(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    files = []
    cv_path = _abs_data_path(application["cv_path"])
    cover_path = _abs_data_path(application["cover_path"])
    if cv_path and cv_path.is_file():
        files.append((cv_path, "CV.pdf"))
    if cover_path and cover_path.is_file():
        files.append((cover_path, "Cover-Letter.pdf"))
    for doc in _documents_for_ids(set(request.form.getlist("doc_ids"))):
        doc_path = db.UPLOADS_DIR / doc["stored_name"]
        if doc_path.is_file():
            files.append((doc_path, f"documents/{doc['id']}-{doc['original_name']}"))
    details = _job_details_text(application, db.get_profile())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, arcname in files:
            archive.write(source, arcname)
        archive.writestr("job-details.txt", details)
    buffer.seek(0)
    return send_file(
        buffer, mimetype="application/zip", as_attachment=True,
        download_name=f"application-{application_id}.zip",
    )


@app.post("/applications/<int:application_id>/send")
def send_application(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    if application["status"] == "sent" and request.form.get("force") != "1":
        flash("این درخواست قبلاً ارسال شده است.", "info")
        return redirect(url_for("application_detail", application_id=application_id))
    compose = {
        "to": request.form.get("to", "").strip(),
        "subject": request.form.get("subject", "").strip(),
        "body": request.form.get("body", "").strip(),
    }
    selected_docs = _documents_for_ids(set(request.form.getlist("doc_ids")))
    attachments = []
    cv_path = _abs_data_path(application["cv_path"])
    cover_path = _abs_data_path(application["cover_path"])
    if cv_path and cv_path.is_file():
        attachments.append((cv_path, "CV.pdf"))
    if cover_path and cover_path.is_file():
        attachments.append((cover_path, "Cover-Letter.pdf"))
    if not attachments:
        error = "فایل PDF رزومه یا کاور لتر پیدا نشد؛ ابتدا نسخه اختصاصی را بسازید."
        return _application_view(application_id, compose, error), 400
    for doc in selected_docs:
        doc_path = db.UPLOADS_DIR / doc["stored_name"]
        if doc_path.is_file():
            attachments.append((doc_path, doc["original_name"] or doc_path.name))
    if not emailer.smtp_ready(g.settings):
        error = "تنظیمات SMTP کامل نیست. ابتدا در تنظیمات، ایمیل فرستنده و سرور را پیکربندی کنید."
        return _application_view(application_id, compose, error), 400
    try:
        emailer.send(g.settings, compose["to"], compose["subject"], compose["body"], attachments)
    except emailer.EmailError as exc:
        return _application_view(application_id, compose, str(exc)), 400
    sent_files = [name for _, name in attachments]
    db.update_application(application_id, {
        "status": "sent",
        "sent_at": db.now_iso(),
        "sent_to": compose["to"],
        "sent_subject": compose["subject"],
        "sent_body": compose["body"],
        "sent_files": sent_files,
    })
    db.update_job(application["job_id"], {"status": "applied"})
    flash("درخواست با موفقیت ارسال شد و در آرشیو ثبت گردید.", "success")
    return redirect(url_for("application_detail", application_id=application_id))


@app.post("/applications/<int:application_id>/delete")
def delete_application_route(application_id):
    application = db.get_application(application_id)
    if not application:
        abort(404)
    db.delete_application(application_id)
    folder = db.GENERATED_DIR / f"job-{application['job_id']}"
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    flash("درخواست و فایل‌های آن حذف شد.", "success")
    return redirect(url_for("applications_page"))


# ---------- settings ----------

def _save_ai_form(form):
    values = {
        "ai_enabled": "1" if form.get("ai_enabled") else "0",
        "ai_base_url": form.get("ai_base_url", "").strip(),
        "ai_model": form.get("ai_model", "").strip(),
    }
    if form.get("clear_ai_key"):
        values["ai_api_key"] = ""
    elif form.get("ai_api_key", "").strip():
        values["ai_api_key"] = form.get("ai_api_key", "").strip()
    db.save_settings(values)
    return db.get_settings()


def _save_smtp_form(form):
    values = {
        "smtp_host": form.get("smtp_host", "").strip(),
        "smtp_port": form.get("smtp_port", "").strip() or "587",
        "smtp_security": form.get("smtp_security", "starttls"),
        "smtp_user": form.get("smtp_user", "").strip(),
        "smtp_from_name": form.get("smtp_from_name", "").strip(),
        "smtp_from_email": form.get("smtp_from_email", "").strip(),
    }
    if form.get("clear_smtp_password"):
        values["smtp_password"] = ""
    elif form.get("smtp_password"):
        values["smtp_password"] = form.get("smtp_password")
    db.save_settings(values)
    return db.get_settings()


@app.get("/settings")
def settings_page():
    return render_template("settings.html", data_dir=str(db.DATA_DIR))


@app.post("/settings")
def save_settings_route():
    section = request.form.get("section", "")
    if section == "ai":
        _save_ai_form(request.form)
        flash("تنظیمات هوش مصنوعی ذخیره شد.", "success")
        return redirect(url_for("settings_page") + "#ai")
    if section == "smtp":
        _save_smtp_form(request.form)
        flash("تنظیمات ایمیل ذخیره شد.", "success")
        return redirect(url_for("settings_page") + "#smtp")
    flash("بخش تنظیمات نامعتبر است.", "error")
    return redirect(url_for("settings_page"))


@app.post("/settings/test-ai")
def test_ai_connection():
    settings = _save_ai_form(request.form)
    ok, message = ai.test_connection(settings)
    flash(message, "success" if ok else "error")
    return redirect(url_for("settings_page") + "#ai")


@app.post("/settings/test-smtp")
def test_smtp_connection():
    settings = _save_smtp_form(request.form)
    ok, message = emailer.test_connection(settings)
    flash(message, "success" if ok else "error")
    return redirect(url_for("settings_page") + "#smtp")


@app.get("/settings/backup")
def backup_data():
    buffer = io.BytesIO()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if db.DB_PATH.is_file():
            archive.write(db.DB_PATH, "data/resumeyar.db")
        for folder_name, folder in (("uploads", db.UPLOADS_DIR), ("generated", db.GENERATED_DIR)):
            if not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if path.is_file():
                    archive.write(path, f"data/{folder_name}/{path.relative_to(folder).as_posix()}")
        archive.writestr(
            "README.txt",
            "ResumeYar local backup. The database contains your profile, jobs, applications, "
            "AI key and SMTP settings. Keep this file private.",
        )
    buffer.seek(0)
    return send_file(
        buffer, mimetype="application/zip", as_attachment=True,
        download_name=f"resumeyar-backup-{stamp}.zip",
    )


# ---------- api ----------

@app.post("/api/fetch-job")
def api_fetch_job():
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"error": "لینک آگهی را وارد کنید."}), 400
    try:
        data = jobsource.fetch_job_from_url(url)
    except jobsource.JobSourceError as exc:
        return jsonify({"error": str(exc)}), 400
    data["description"] = data.get("description", "")[:20000]
    return jsonify(data)


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


# ---------- errors ----------

@app.errorhandler(400)
def bad_request(error):
    message = getattr(error, "description", "درخواست نامعتبر است.")
    return render_template("error.html", code=400, message=message), 400


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="صفحه یا فایل موردنظر پیدا نشد."), 404


@app.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return render_template("error.html", code=413,
                           message="حجم آپلود بیشتر از حد مجاز (۲۵ مگابایت) است."), 413


@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", code=500,
                           message="خطای غیرمنتظره‌ای رخ داد. دوباره تلاش کنید."), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5533"))
    host = os.environ.get("HOST", "127.0.0.1")
    if os.environ.get("RESUMEYAR_NO_BROWSER") != "1" and host in ("127.0.0.1", "localhost"):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
