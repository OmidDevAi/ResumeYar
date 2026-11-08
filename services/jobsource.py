import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from utils import (
    analyze_match, clean_html_text, detect_language, summarize_job_text, tokenize,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8"}


class JobSourceError(Exception):
    pass


def _request_json(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise JobSourceError(f"دریافت آگهی‌ها ناموفق بود: {exc}") from exc
    except ValueError as exc:
        raise JobSourceError("پاسخ منبع آگهی قابل خواندن نبود.") from exc


def _json_ld_job(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" not in types:
                continue
            org = item.get("hiringOrganization") or {}
            if isinstance(org, list):
                org = org[0] if org else {}
            location = ""
            job_location = item.get("jobLocation") or {}
            if isinstance(job_location, list):
                job_location = job_location[0] if job_location else {}
            address = (job_location or {}).get("address") or {}
            if isinstance(address, dict):
                location = "، ".join(str(address.get(key, "")).strip()
                                     for key in ("addressLocality", "addressRegion")
                                     if str(address.get(key, "")).strip())
            elif isinstance(address, str):
                location = address
            description = item.get("description", "")
            text = clean_html_text(description) if "<" in description else str(description)
            return {
                "title": str(item.get("title", "")).strip(),
                "company": str((org or {}).get("name", "")).strip(),
                "location": location,
                "description": text.strip(),
            }
    return None


def _meta(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _clean_title(title, site_name):
    title = re.sub(r"\s+", " ", title or "").strip()
    title = re.sub(r"\s*[|\-–—]\s*(جابینجا|جاب‌ویژن|ای‌استخدام|دیوار|لینکدین|LinkedIn).*$", "", title, flags=re.I)
    if site_name and title.lower().endswith(site_name.lower()):
        title = title[: -len(site_name)].strip(" |–—-")
    return title


def fetch_job_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise JobSourceError("لینک معتبر نیست. آدرس باید با http یا https شروع شود.")
    try:
        response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise JobSourceError(f"باز کردن لینک ناموفق بود: {exc}") from exc
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "<html" not in response.text[:1000].lower():
        raise JobSourceError("این لینک یک صفحه وب نیست؛ متن آگهی را دستی وارد کنید.")
    soup = BeautifulSoup(response.text, "html.parser")
    site_name = _meta(soup, "og:site_name")
    structured = _json_ld_job(soup)
    if structured and structured.get("title"):
        description = structured.get("description", "")
        result = {
            "title": structured["title"],
            "company": structured.get("company", ""),
            "location": structured.get("location", ""),
            "description": summarize_job_text(description, 15000),
            "source": parsed.netloc.replace("www.", ""),
            "url": response.url,
        }
    else:
        title = _meta(soup, "og:title") or (soup.title.string if soup.title else "")
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(" ", strip=True) if h1 else ""
        title = _clean_title(title, site_name)
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer",
                         "aside", "form", "svg", "iframe", "button"]):
            tag.decompose()
        container = soup.find("main") or soup.find("article") or soup.body or soup
        description = container.get_text("\n", strip=True)
        description = re.sub(r"\n{3,}", "\n\n", description)
        result = {
            "title": title.strip()[:300],
            "company": "",
            "location": "",
            "description": summarize_job_text(description, 15000),
            "source": parsed.netloc.replace("www.", ""),
            "url": response.url,
        }
    emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", result["description"])
    result["contact_email"] = emails[0] if emails else ""
    result["language"] = detect_language(result["title"] + " " + result["description"])
    if len(result["description"]) < 60:
        raise JobSourceError("متن کافی از این صفحه استخراج نشد؛ آگهی را دستی وارد کنید.")
    return result


def _match_query(text, query):
    if not query.strip():
        return True
    query_tokens = tokenize(query)
    if not query_tokens:
        return True
    text_tokens = set(tokenize(text))
    return any(token in text_tokens for token in query_tokens)


def _remoteok(query):
    data = _request_json("https://remoteok.com/api")
    if not isinstance(data, list):
        raise JobSourceError("ساختار پاسخ RemoteOK غیرمنتظره بود.")
    jobs = []
    for item in data:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        text = f"{item.get('position', '')} {item.get('description', '')} {' '.join(item.get('tags', []) or [])}"
        if not _match_query(text, query):
            continue
        jobs.append({
            "title": item.get("position", ""),
            "company": item.get("company", ""),
            "location": item.get("location", "") or "Remote",
            "description": summarize_job_text(clean_html_text(item.get("description", "")), 12000),
            "url": item.get("url", "") or item.get("apply_url", ""),
            "source": "RemoteOK",
            "language": "en",
        })
        if len(jobs) >= 30:
            break
    return jobs


def _arbeitnow(query):
    data = _request_json("https://www.arbeitnow.com/api/job-board-api")
    items = data.get("data", []) if isinstance(data, dict) else []
    jobs = []
    for item in items:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        text = f"{item.get('title', '')} {item.get('description', '')} {' '.join(item.get('tags', []) or [])}"
        if not _match_query(text, query):
            continue
        location = item.get("location", "") or ("Remote" if item.get("remote") else "")
        jobs.append({
            "title": item.get("title", ""),
            "company": item.get("company_name", ""),
            "location": location,
            "description": summarize_job_text(clean_html_text(item.get("description", "")), 12000),
            "url": item.get("url", ""),
            "source": "Arbeitnow",
            "language": "en",
        })
        if len(jobs) >= 30:
            break
    return jobs


def _jobicy(query):
    data = _request_json("https://jobicy.com/api/v2/remote-jobs?count=50")
    items = data.get("jobs", []) if isinstance(data, dict) else []
    jobs = []
    for item in items:
        if not isinstance(item, dict) or not item.get("jobTitle"):
            continue
        text = f"{item.get('jobTitle', '')} {item.get('jobExcerpt', '')} {item.get('jobDescription', '')}"
        if not _match_query(text, query):
            continue
        jobs.append({
            "title": item.get("jobTitle", ""),
            "company": item.get("companyName", ""),
            "location": item.get("jobGeo", "") or "Remote",
            "description": summarize_job_text(clean_html_text(item.get("jobDescription", "")), 12000),
            "url": item.get("url", ""),
            "source": "Jobicy",
            "language": "en",
        })
        if len(jobs) >= 30:
            break
    return jobs


SOURCES = {
    "remoteok": ("RemoteOK", _remoteok, "آگهی‌های ریموت بین‌المللی (انگلیسی)"),
    "arbeitnow": ("Arbeitnow", _arbeitnow, "آگهی‌های اروپا و ریموت (انگلیسی)"),
    "jobicy": ("Jobicy", _jobicy, "موقعیت‌های ریموت متنوع (انگلیسی)"),
}


def discover(source, query, profile, limit=10, work_mode=""):
    if source not in SOURCES:
        raise JobSourceError("منبع انتخاب‌شده معتبر نیست.")
    _, fetcher, _ = SOURCES[source]
    matched = []
    for job in fetcher(query):
        job.update(analyze_match(profile, job))
        if not job.get("work_mode"):  # built-in feeds are remote-only
            job["work_mode"] = "remote"
            job.update(analyze_match(profile, job))
        if work_mode and job.get("work_mode") != work_mode:
            continue
        job["status"] = "new"
        matched.append(job)
    matched.sort(key=lambda item: item.get("score", 0), reverse=True)
    return matched[:limit]
