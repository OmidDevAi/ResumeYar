import re
from pathlib import Path

from utils import detect_skills_in_text, split_list


class CVParserError(Exception):
    pass


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?98|0)?[\s\-().]?9\d{2}[\s\-().]?\d{3}[\s\-().]?\d{4}")
URL_RE = re.compile(r"https?://[^\s<>\"')]+|(?:www\.)[^\s<>\"')]+", re.I)


def _docx_text_stdlib(path):
    """Read DOCX with the standard library so mobile builds can skip lxml/python-docx."""
    import xml.etree.ElementTree as ET
    import zipfile

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise CVParserError("فایل DOCX معتبر نیست یا آسیب دیده است.") from exc
    root = ET.fromstring(xml)
    lines = []
    for paragraph in root.iter(f"{ns}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{ns}t":
                parts.append(node.text or "")
            elif node.tag in (f"{ns}tab", f"{ns}br"):
                parts.append(" ")
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _docx_text(path):
    try:
        from docx import Document
    except ImportError:
        return _docx_text_stdlib(path)
    document = Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def extract_text(path):
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages[:30]:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages)
        elif suffix == ".docx":
            text = _docx_text(path)
        elif suffix in (".txt", ".md"):
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raise CVParserError("فقط فایل PDF، DOCX یا TXT برای خواندن خودکار پشتیبانی می‌شود.")
    except CVParserError:
        raise
    except Exception as exc:
        raise CVParserError(f"خواندن فایل ناموفق بود: {exc}") from exc
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise CVParserError("متنی داخل فایل پیدا نشد؛ اگر فایل اسکن‌شده است، نسخه متنی PDF را بارگذاری کنید.")
    return text


def heuristic_profile(text):
    text = text or ""
    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)
    urls = URL_RE.findall(text)
    links = []
    for url in urls:
        lowered = url.lower()
        if any(host in lowered for host in ("linkedin", "github", "gitlab", "portfolio", "behance", "dribbble")):
            if url not in links:
                links.append(url)

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    name = ""
    headline = ""
    skip_words = ("رزومه", "resume", "curriculum", "vitae", "cv", "سوابق", "اطلاعات")
    for index, line in enumerate(lines[:12]):
        if len(line) > 70 or EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line):
            continue
        lowered = line.lower()
        if any(word in lowered for word in skip_words) and len(line) < 40:
            continue
        if len(line.split()) <= 6:
            letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", line))
            if letters >= max(4, len(line) * 0.5):
                name = line.strip(" |:-")
                for next_line in lines[index + 1:index + 5]:
                    if any(word in next_line.lower() for word in skip_words):
                        continue
                    if len(next_line) <= 80 and not EMAIL_RE.search(next_line) and not PHONE_RE.search(next_line):
                        headline = next_line.strip(" |:-")
                        break
                break

    skills = detect_skills_in_text(text, 24)
    return {
        "full_name": name,
        "headline": headline,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "city": "",
        "links": "\n".join(links[:4]),
        "skills": "، ".join(skills[:20]),
        "summary": "",
        "experiences": [],
        "education": [],
        "languages": "",
    }


def profile_payload_from_cv(text, ai_profile=None):
    payload = heuristic_profile(text)
    if ai_profile:
        for key in ("full_name", "headline", "email", "phone", "city", "links", "summary", "languages"):
            value = ai_profile.get(key)
            if isinstance(value, str) and value.strip():
                payload[key] = value.strip()
        skills = ai_profile.get("skills")
        if isinstance(skills, list) and skills:
            payload["skills"] = "، ".join(str(s).strip() for s in skills if str(s).strip())[:2000]
        for key in ("experiences", "education"):
            items = ai_profile.get(key)
            if isinstance(items, list) and items:
                payload[key] = items
    payload["cv_text"] = text[:30000]
    return payload
