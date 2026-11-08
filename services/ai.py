import json
import re

from utils import split_list


class AIError(Exception):
    pass


def ai_ready(settings):
    if settings.get("ai_enabled") != "1":
        return False
    if not settings.get("ai_base_url") or not settings.get("ai_model"):
        return False
    key = settings.get("ai_api_key", "").strip()
    base = settings.get("ai_base_url", "")
    local = any(host in base for host in ("localhost", "127.0.0.1", "0.0.0.0"))
    return bool(key or local)


def _client(settings):
    if not ai_ready(settings):
        raise AIError("هوش مصنوعی فعال نیست یا کلید API تنظیم نشده است.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AIError("کتابخانه openai نصب نیست. requirements.txt را دوباره نصب کنید.") from exc
    base_url = settings.get("ai_base_url", "").strip() or None
    api_key = settings.get("ai_api_key", "").strip() or "local"
    try:
        return OpenAI(api_key=api_key, base_url=base_url, timeout=90, max_retries=1)
    except Exception as exc:
        raise AIError(f"اتصال به سرویس هوش مصنوعی ناموفق بود: {exc}") from exc


def _parse_json(content):
    if not content:
        raise AIError("پاسخ خالی از سرویس هوش مصنوعی دریافت شد.")
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise AIError("پاسخ هوش مصنوعی قابل خواندن نبود. دوباره تلاش کنید.")


def _http_chat(settings, messages, temperature=0.35, max_tokens=None):
    """OpenAI-compatible chat over plain HTTP, used where the openai SDK is not bundled."""
    try:
        import requests
    except ImportError as exc:
        raise AIError("کتابخانه ارتباط با هوش مصنوعی نصب نیست.") from exc
    base = settings.get("ai_base_url", "").strip().rstrip("/")
    if not base:
        raise AIError("آدرس سرویس هوش مصنوعی تنظیم نشده است.")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    payload = {
        "model": settings.get("ai_model", "gpt-4o-mini"),
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    headers = {"Content-Type": "application/json"}
    key = settings.get("ai_api_key", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=90)
    except requests.RequestException as exc:
        raise AIError(f"درخواست به هوش مصنوعی ناموفق بود: {exc}") from exc
    if response.status_code >= 400:
        detail = (response.text or "").strip()
        if len(detail) > 300:
            detail = detail[:300] + "…"
        raise AIError(f"سرویس هوش مصنوعی خطا داد ({response.status_code}): {detail}")
    try:
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIError("پاسخ هوش مصنوعی قابل خواندن نبود.") from exc


def _chat(settings, system, user, temperature=0.35, max_tokens=None):
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        from openai import OpenAI  # noqa: F401
    except ImportError:
        return _http_chat(settings, messages, temperature=temperature, max_tokens=max_tokens)
    client = _client(settings)
    try:
        kwargs = {"model": settings.get("ai_model", "gpt-4o-mini"),
                  "messages": messages, "temperature": temperature}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as exc:
        message = str(exc)
        if len(message) > 300:
            message = message[:300] + "…"
        raise AIError(f"درخواست به هوش مصنوعی ناموفق بود: {message}") from exc


def test_connection(settings):
    if not ai_ready(settings):
        return False, "ابتدا کلید API و مدل را ذخیره و گزینه هوش مصنوعی را فعال کنید."
    try:
        text = _chat(
            settings, "You are a health check.",
            "Reply with the single word: OK", temperature=0, max_tokens=5,
        ).strip()
        return True, f"اتصال برقرار است (پاسخ مدل: {text[:40]})"
    except Exception as exc:
        return False, f"اتصال ناموفق: {str(exc)[:250]}"


TAILOR_SYSTEM = """You are an expert career writer and ATS optimization assistant.
You help a candidate tailor an existing CV and cover letter to a specific job.

STRICT RULES:
- Use ONLY facts present in the candidate profile. Never invent employers, job titles, dates,
  degrees, skills, certifications, metrics, or achievements.
- You may reorder skills, select the most relevant existing skills, and rewrite the summary
  and cover letter using existing facts.
- The skills list must be a subset of skills explicitly present in the candidate profile.
- Do not use markdown, bullet symbols, or placeholders such as [company].
- Write all output in the requested target language.
- The cover letter must be 3-4 short paragraphs, professional, specific to the target role and
  company, and ready to send. Do not exaggerate.
- Return ONLY a valid JSON object with exactly these keys:
  {"headline": "string", "summary": "string", "skills": ["string"], "cover_letter": "string"}
"""


def tailor(profile, job, language, settings):
    skills = split_list(profile.get("skills", ""))
    language_name = "Persian (Farsi)" if language == "fa" else "English"
    profile_payload = {
        "full_name": profile.get("full_name", ""),
        "headline": profile.get("headline", ""),
        "city": profile.get("city", ""),
        "summary": profile.get("summary", ""),
        "skills": skills,
        "languages": profile.get("languages", ""),
        "experiences": profile.get("experiences", []),
        "education": profile.get("education", []),
    }
    job_payload = {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "description": (job.get("description", "") or "")[:9000],
    }
    user = (
        f"TARGET LANGUAGE: {language_name}\n\n"
        f"CANDIDATE PROFILE:\n{json.dumps(profile_payload, ensure_ascii=False)}\n\n"
        f"TARGET JOB:\n{json.dumps(job_payload, ensure_ascii=False)}\n\n"
        "Produce a tailored professional headline (keep the candidate's real seniority level), "
        "a concise summary (max 65 words), a reordered skills list, and a complete cover letter. "
        "Return JSON only."
    )
    data = _parse_json(_chat(settings, TAILOR_SYSTEM, user))
    summary = str(data.get("summary", "")).strip()
    cover_letter = str(data.get("cover_letter", "")).strip()
    headline = str(data.get("headline", "")).strip() or profile.get("headline", "").strip()
    if not summary or not cover_letter:
        raise AIError("پاسخ هوش مصنوعی ناقص بود؛ دوباره تلاش کنید.")

    candidate_skills = {s.casefold().strip(): s for s in skills}
    chosen = []
    for item in data.get("skills", []) or []:
        key = str(item).casefold().strip()
        if key in candidate_skills and candidate_skills[key] not in chosen:
            chosen.append(candidate_skills[key])
    for skill in skills:
        if skill not in chosen:
            chosen.append(skill)

    return {
        "headline": headline,
        "summary": summary[:2000],
        "skills": chosen,
        "cover_letter": cover_letter[:9000],
        "mode": "ai",
    }


EXTRACT_SYSTEM = """You extract structured data from a CV. Use only information explicitly present.
Never invent facts. Missing values must be empty strings or empty arrays.
Return ONLY valid JSON with this schema:
{
  "full_name": "string",
  "headline": "string",
  "email": "string",
  "phone": "string",
  "city": "string",
  "links": "string (newline separated URLs)",
  "summary": "string (the candidate's own summary, or empty)",
  "skills": ["string"],
  "languages": "string (comma separated)",
  "experiences": [
    {"title": "string", "company": "string", "location": "string",
     "start": "string", "end": "string", "bullets": ["string"]}
  ],
  "education": [
    {"degree": "string", "field": "string", "school": "string",
     "start": "string", "end": "string"}
  ]
}
Keep bullet points verbatim or lightly cleaned; do not add achievements.
"""


def extract_profile(cv_text, settings):
    text = (cv_text or "")[:18000]
    if not text.strip():
        raise AIError("متنی برای تحلیل وجود ندارد.")
    data = _parse_json(_chat(settings, EXTRACT_SYSTEM, "CV TEXT:\n" + text))
    clean = {}
    for key in ("full_name", "headline", "email", "phone", "city", "links", "summary", "languages"):
        value = data.get(key, "")
        clean[key] = str(value).strip() if isinstance(value, (str, int, float)) else ""
    skills = data.get("skills", [])
    clean["skills"] = [str(s).strip() for s in skills if str(s).strip()][:40] if isinstance(skills, list) else []

    def clean_experiences(items):
        result = []
        if not isinstance(items, list):
            return result
        for item in items[:12]:
            if not isinstance(item, dict):
                continue
            bullets = item.get("bullets", [])
            if not isinstance(bullets, list):
                bullets = []
            result.append({
                "title": str(item.get("title", "")).strip()[:200],
                "company": str(item.get("company", "")).strip()[:200],
                "location": str(item.get("location", "")).strip()[:120],
                "start": str(item.get("start", "")).strip()[:40],
                "end": str(item.get("end", "")).strip()[:40],
                "bullets": [str(b).strip()[:600] for b in bullets if str(b).strip()][:10],
            })
        return [item for item in result if item["title"] or item["company"]]

    def clean_education(items):
        result = []
        if not isinstance(items, list):
            return result
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            result.append({
                "degree": str(item.get("degree", "")).strip()[:150],
                "field": str(item.get("field", "")).strip()[:150],
                "school": str(item.get("school", "")).strip()[:200],
                "start": str(item.get("start", "")).strip()[:40],
                "end": str(item.get("end", "")).strip()[:40],
            })
        return [item for item in result if item["degree"] or item["school"]]

    clean["experiences"] = clean_experiences(data.get("experiences", []))
    clean["education"] = clean_education(data.get("education", []))
    return clean
