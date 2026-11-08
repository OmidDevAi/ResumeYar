import re
import html as html_module
from datetime import datetime
from urllib.parse import quote_plus

import jdatetime

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)

WORK_MODES = {
    "onsite": "حضوری",
    "hybrid": "ترکیبی",
    "remote": "دورکاری",
}
EMPLOYMENT_TYPES = {
    "full_time": "تمام‌وقت",
    "part_time": "پاره‌وقت",
    "contract": "پیمانکاری / برون‌سپاری",
    "freelance": "فریلنس / پروژه‌ای",
    "internship": "کارآموزی",
}
_WORK_MODE_HINTS = (
    ("remote", (
        "remote", "work from home", "work-from-home", "wfh", "anywhere",
        "telecommute", "دورکاری", "دور کاری", "ریموت", "از راه دور",
        "غیرحضوری", "غیر حضوری",
    )),
    ("hybrid", ("hybrid", "ترکیبی", "نیمه حضوری", "نیمه‌حضوری")),
    ("onsite", ("onsite", "on-site", "in office", "in-office", "حضوری", "در محل دفتر")),
)
_EMPLOYMENT_HINTS = (
    ("part_time", ("part-time", "part time", "پاره وقت", "پاره‌وقت", "نیمه وقت", "نیمه‌وقت")),
    ("freelance", ("freelance", "freelancer", "فریلنس", "فریلنسری", "پروژه‌ای", "پروژه ای")),
    ("contract", (
        "contract", "contractor", "outsourcing", "outsourced",
        "پیمانکاری", "برون سپاری", "برون‌سپاری", "قرارداد پروژه",
    )),
    ("internship", ("internship", "کارآموزی", "کارآموز")),
    ("full_time", ("full-time", "full time", "تمام وقت", "تمام‌وقت")),
)
LINKEDIN_WORK_MODE = {"onsite": "1", "remote": "2", "hybrid": "3"}
LINKEDIN_JOB_TYPE = {
    "full_time": "F", "part_time": "P", "contract": "C",
    "freelance": "C", "internship": "I",
}

STOPWORDS = {
    # Persian
    "و", "در", "به", "از", "که", "این", "آن", "را", "با", "برای", "است", "هست",
    "می", "می‌شود", "شود", "شد", "شده", "باشد", "باشند", "بود", "بودن", "کرد",
    "کردن", "کند", "کنند", "دارد", "دارند", "داشتن", "یک", "تا", "هم", "یا",
    "بر", "اما", "اگر", "چون", "پس", "نیز", "خود", "ما", "شما", "او", "آنها",
    "من", "تو", "های", "هایی", "ها", "های", "ای", "علاوه", "طبق", "ضمن",
    "درباره", "بین", "درون", "روی", "زیر", "پیش", "پس", "همه", "هیچ", "دیگر",
    "بسیار", "خیلی", "حداقل", "حداکثر", "بیش", "کم", "تر", "ترین", "قابل",
    "لازم", "مناسب", "مورد", "جهت", "خصوص", "نسبت", "مثل", "مانند", "چنین",
    "همچنین", "بنابراین", "لذا", "ولی", "و", "نه", "بله", "آیا", "چگونه",
    "چه", "کجا", "کی", "چرا", "کدام", "هر", "همان", "ایشان", "وی", "ما",
    "شرکت", "موقعیت", "شغل", "شغلی", "کاری", "کار", "استخدام", "استخدامی",
    "آگهی", "فرصت", "فرصت‌های", "تیم", "تیمی", "نقش", "عنوان", "حوزه",
    "رشته", "سابقه", "سال", "سال‌های", "ماه", "هفته", "روز", "ساعت", "تمام",
    "وقت", "پاره", "دورکاری", "حضوری", "امکان", "نیاز", "نیازمند", "داشتن",
    "نیازمندی", "نیازمندی‌ها", "پیشرفته", "مقدماتی", "کامل",
    "آشنا", "آشنایی", "تسلط", "مسلط", "توانایی", "توانمند", "مهارت", "مهارت‌های",
    "ویژگی", "ویژگی‌های", "وظایف", "مسئولیت", "مسئولیت‌ها", "شرح", "مزایا",
    "بیمه", "حقوق", "مزیت", "اولویت", "ترجیح", "الزامی", "مزایای", "ارسال",
    "رزومه", "درخواست", "همکاری", "داوطلب", "متقاضی", "خانم", "آقا", "خانم‌ها",
    "آقایان", "جنسیت", "سن", "سابقه‌ی", "حدود", "بالا", "پایین", "عنوان‌های",
    "کارشناس", "کارشناسی", "مدیر", "مدیریت", "ارشد", "سرپرست", "مربی", "مسئول",
    "برنامه", "برنامه‌ریزی", "اجرا", "اجرایی", "گزارش", "گزارش‌گیری", "تحلیل",
    "تحلیل‌گر", "توسعه", "بهبود", "پیاده", "سازی", "طراحی", "پیگیری", "کنترل",
    "بررسی", "شناسایی", "جذب", "آموزش", "ارائه", "ایجاد", "نظارت", "هماهنگی",
    "پشتیبانی", "مشاوره", "فروش", "بازاریابی", "بازار", "مشتری", "مشتریان",
    "محصول", "خدمات", "خدمت", "کیفیت", "فرآیند", "فرایند", "پروژه", "پروژه‌ها",
    "سیستم", "سیستم‌ها", "اطلاعات", "داده", "داده‌ها", "گزارش‌ها", "اسناد",
    "مدارک", "فایل", "فایل‌ها", "نرم", "افزار", "نرم‌افزار", "سایت", "وب",
    "آنلاین", "حرفه‌ای", "حرفه‌ای‌", "عمومی", "اختصاصی", "داخلی", "خارجی",
    "ایران", "تهران", "شهر", "استان", "منطقه", "دفتر", "شعبه", "سازمان",
    "مجموعه", "گروه", "هلدینگ", "کارفرما", "کارفرمای", "محترم", "گرامی",
    "دوست", "عزیز", "علاقه‌مند", "علاقه‌مندان", "متقاضیان", "لطفا", "لطفاً",
    "خواهشمند", "ممنون", "سپاس", "موفق", "موفقیت", "بهترین", "عالی", "خوب",
    "جدید", "قدیم", "اول", "دوم", "سوم", "چهارم", "پنجم", "ششم", "هفتم",
    "هشتم", "نهم", "دهم", "یکم", "دو", "سه", "چهار", "پنج", "شش", "هفت",
    "هشت", "نه", "ده", "صد", "هزار", "میلیون", "تومان", "ریال", "درصد",
    "میان", "وسط", "طی", "مدت", "طول", "مدت‌زمان", "زمان", "زمانی", "بازه",
    "شامل", "شاملِ", "عبارت", "قبیل", "جمله", "طور", "گونه", "شکل", "حال",
    "صورت", "واقع", "اصل", "اصلی", "کلی", "جزئی", "مهم", "مهم‌ترین", "کاربردی",
    "تخصصی", "عملی", "علمی", "دانش", "دانشجو", "دانشگاه", "فارغ", "التحصیل",
    "مدرک", "لیسانس", "فوق", "دیپلم", "دکتری", "کارشناسی‌ارشد", "زبان",
    "انگلیسی", "فارسی", "مسلط", "سطح", "دوره", "کلاس", "گواهی", "مدرک",
    # English
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "has", "this", "that", "from", "they", "their", "them", "who", "what",
    "when", "where", "which", "while", "into", "over", "under", "about",
    "into", "onto", "also", "more", "most", "other", "such", "than", "then",
    "there", "these", "those", "been", "being", "was", "were", "not", "but",
    "all", "any", "can", "may", "must", "should", "would", "could", "able",
    "work", "working", "role", "job", "jobs", "position", "company", "team",
    "teams", "candidate", "candidates", "applicant", "requirements", "required",
    "responsibilities", "skills", "experience", "years", "year", "month",
    "day", "full", "part", "time", "remote", "hybrid", "onsite", "office",
    "opportunity", "opportunities", "benefits", "salary", "please", "apply",
    "application", "send", "resume", "cv", "cover", "letter", "looking",
    "join", "new", "good", "great", "strong", "plus", "preferred", "nice",
    "must", "ideal", "ideal", "well", "using", "use", "used", "like", "across",
    "within", "without", "including", "include", "included", "based", "per",
    "per", "via", "etc", "e.g", "eg", "ie", "i.e", "one", "two", "three",
    "four", "five", "six", "seven", "eight", "nine", "ten", "first", "last",
    "degree", "bachelor", "master", "university", "field", "related", "least",
    "knowledge", "understanding", "ability", "responsible", "ensure", "help",
    "build", "building", "develop", "development", "support", "provide",
    "manage", "management", "business", "client", "clients", "customer",
    "customers", "product", "products", "service", "services", "market",
    "marketing", "sales", "data", "information", "system", "systems",
    "software", "tools", "tool", "environment", "fast", "paced", "growing",
    "global", "world", "people", "person", "professional", "high", "level",
}

SKILL_VOCAB = [
    # finance / accounting
    "حسابداری", "حسابرسی", "مالی", "مالیات", "بیمه", "حقوق و دستمزد", "بودجه‌بندی",
    "بودجه", "صورت‌های مالی", "حسابداری مالی", "حسابداری صنعتی", "حسابداری دولتی",
    "حسابداری انبار", "کنترل داخلی", "مدیریت ریسک", "تحلیل مالی", "گزارش‌های مالی",
    "اکسل", "Excel", "Advanced Excel", "Pivot Table", "Power Query", "VBA",
    "نرم‌افزار هلو", "هلو", "سپیدار", "پارسیان", "رایورز", "همکاران سیستم",
    "QuickBooks", "SAP", "Oracle ERP", "ERP", "Tally", "Xero", "Odoo",
    "بهای تمام شده", "انبارگردانی", "خزانه", "دریافت و پرداخت", "تنخواه",
    "چک", "اسناد تجاری", "فاکتور", "صورتحساب", "اظهارنامه", "ارزش افزوده",
    "بیمه تأمین اجتماعی", "بیمه تکمیلی", "قانون کار", "مالیات بر درآمد",
    "پیش‌بینی مالی", "Financial Reporting", "Bookkeeping", "Payroll",
    "Taxation", "Auditing", "Budgeting", "Forecasting", "Accounts Payable",
    "Accounts Receivable", "Financial Analysis", "Cost Accounting",
    "Internal Controls", "Risk Management", "Inventory Management",
    # office / admin
    "Microsoft Office", "Word", "PowerPoint", "Outlook", "Office",
    "تایپ", "تایپ سریع", "نامه‌نگاری", "بایگانی", "ثبت اسناد", "امور اداری",
    "منشی‌گری", "پذیرش", "تشریفات", "مدیریت زمان", "برنامه‌ریزی",
    "مهارت ارتباطی", "ارتباطات", "مذاکره", "حل مسئله", "کار تیمی", "تیم‌ورک",
    "رهبری", "Leadership", "Communication", "Negotiation", "Problem Solving",
    "Time Management", "Teamwork", "Organization", "Scheduling", "Data Entry",
    "CRM", "Customer Service", "پشتیبانی مشتری", "خدمات مشتریان",
    # tech / data
    "Python", "SQL", "MySQL", "PostgreSQL", "SQLite", "MongoDB", "Redis",
    "Django", "Flask", "FastAPI", "JavaScript", "TypeScript", "React", "Vue.js",
    "Next.js", "Node.js", "HTML", "CSS", "Bootstrap", "Tailwind", "PHP",
    "Laravel", "Java", "C#", "C++", "Go", "Git", "GitHub", "Docker",
    "Kubernetes", "Linux", "AWS", "Azure", "Google Cloud", "DevOps", "CI/CD",
    "REST API", "API", "GraphQL", "Machine Learning", "Deep Learning",
    "Data Science", "Data Analysis", "Data Visualization", "Power BI",
    "Tableau", "Pandas", "NumPy", "TensorFlow", "PyTorch", "Scikit-learn",
    "ETL", "Big Data", "Hadoop", "Spark", "Airflow", "Jira", "Agile", "Scrum",
    "Kanban", "Project Management", "Product Management", "UI/UX", "Figma",
    "Adobe XD", "Photoshop", "Illustrator", "Adobe Photoshop", "Canva",
    "Premiere", "After Effects", "WordPress", "SEO", "Google Analytics",
    "Google Ads", "Content Marketing", "Social Media", "Digital Marketing",
    "Email Marketing", "Copywriting", "Content Writing", "گرافیک", "فتوشاپ",
    "طراحی گرافیک", "طراحی سایت", "برنامه‌نویسی", "تحلیل داده", "هوش مصنوعی",
    "یادگیری ماشین", "علم داده", "مدیریت پروژه", "اسکرام", "چابک", "دواپس",
    "شبکه", "Network", "Security", "امنیت اطلاعات", "پشتیبانی شبکه",
    "تعمیر و نگهداری", "Help Desk", "سخت‌افزار", "مونتاژ",
    # sales / marketing
    "فروش", "بازاریابی", "بازاریابی تلفنی", "مذاکره فروش", "مدیریت فروش",
    "توسعه بازار", "تحقیقات بازار", "برندینگ", "تبلیغات", "کپی‌رایتینگ",
    "Sales", "Marketing", "Business Development", "Lead Generation",
    "Market Research", "Branding", "Advertising", "B2B", "B2C",
    # soft skills / general
    "مدیریت تیم", "آموزش", "منابع انسانی", "جذب و استخدام", "کارگزینی",
    "HR", "Recruitment", "Training", "مهارت ارائه", "گزارش‌نویسی",
    "تحقیق و توسعه", "R&D", "کنترل کیفیت", "Quality Assurance", "QC",
    "ISO", "HSE", "ایمنی", "لجستیک", "زنجیره تأمین", "خرید", "تدارکات",
    "انبارداری", "حمل و نقل", "Supply Chain", "Procurement", "Logistics",
]

SKILL_LOOKUP = sorted({s.strip() for s in SKILL_VOCAB if s.strip()}, key=len, reverse=True)

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize(text):
    if not text:
        return ""
    text = html_module.unescape(str(text)).lower()
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = text.translate(_FA_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    text = text.translate(str.maketrans("،؛؟", "   "))
    text = re.sub(r"[\u200c\u200d]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text):
    normalized = normalize(text)
    raw = re.findall(r"[a-z0-9][a-z0-9+#.\-]*|[\u0600-\u06ff]{2,}", normalized)
    tokens = []
    for token in raw:
        token = token.strip(".-")
        if len(token) < 2 or token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def split_list(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        parts = value
    else:
        parts = re.split(r"[,،;\n]+", str(value))
    result, seen = [], set()
    for part in parts:
        item = str(part).strip()
        key = normalize(item)
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def detect_language(text):
    if not text:
        return "fa"
    persian = len(re.findall(r"[\u0600-\u06ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "fa" if persian >= max(3, latin * 0.25) else "en"


def detect_work_traits(job):
    text = normalize(" ".join(
        str(job.get(key, "") or "") for key in ("title", "location", "description")
    ))
    work_mode = ""
    for mode, hints in _WORK_MODE_HINTS:
        if any(normalize(hint) in text for hint in hints):
            work_mode = mode
            break
    employment_type = ""
    for kind, hints in _EMPLOYMENT_HINTS:
        if any(normalize(hint) in text for hint in hints):
            employment_type = kind
            break
    return {"work_mode": work_mode, "employment_type": employment_type}


def _skill_pattern(skill):
    normalized = normalize(skill)
    return re.escape(normalized)


def skill_present(skill, normalized_text):
    normalized = normalize(skill)
    if not normalized or len(normalized) < 2:
        return False
    if re.search(r"[a-z]", normalized):
        pattern = r"(?<![a-z0-9+#.])" + _skill_pattern(skill) + r"(?![a-z0-9+#.])"
        return re.search(pattern, normalized_text) is not None
    return normalized in normalized_text


def detect_skills_in_text(text, limit=40):
    normalized = normalize(text)
    found = []
    for skill in SKILL_LOOKUP:
        if skill_present(skill, normalized):
            found.append(skill)
            if len(found) >= limit:
                break
    return found


def _profile_text(profile):
    parts = [
        profile.get("headline", ""), profile.get("summary", ""),
        profile.get("skills", ""), profile.get("cv_text", ""),
        profile.get("languages", ""),
    ]
    for exp in profile.get("experiences", []) or []:
        parts.extend([exp.get("title", ""), exp.get("company", ""), exp.get("description", "")])
        parts.extend(exp.get("bullets", []) or [])
    for edu in profile.get("education", []) or []:
        parts.extend([edu.get("degree", ""), edu.get("field", ""), edu.get("school", "")])
    return normalize(" ".join(str(p) for p in parts if p))


def top_terms(text, limit=30):
    tokens = tokenize(text)
    counts = {}
    for token in tokens:
        if len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], -len(pair[0])))
    return [word for word, _ in ordered[:limit]]


def _title_score(profile, job_title):
    job_tokens = set(tokenize(job_title))
    if not job_tokens:
        return 0.0
    preferences = profile.get("preferences") or {}
    desired = split_list(preferences.get("titles", ""))
    candidates = desired + ([profile.get("headline", "")] if profile.get("headline") else [])
    best = 0.0
    for candidate in candidates:
        tokens = set(tokenize(candidate))
        if not tokens:
            continue
        overlap = len(tokens & job_tokens)
        best = max(best, overlap / max(1, min(len(tokens), len(job_tokens))))
    return min(1.0, best)


def analyze_match(profile, job):
    title = job.get("title", "") if isinstance(job, dict) else ""
    description = job.get("description", "") if isinstance(job, dict) else ""
    location = job.get("location", "") if isinstance(job, dict) else ""
    job_text = f"{title} {description}"
    normalized_job = normalize(job_text)
    profile_text = _profile_text(profile)
    profile_tokens = set(tokenize(profile_text))
    traits = detect_work_traits(job)
    if isinstance(job, dict):
        traits["work_mode"] = job.get("work_mode") or traits["work_mode"]
        traits["employment_type"] = job.get("employment_type") or traits["employment_type"]

    profile_skills = split_list(profile.get("skills", ""))
    if not profile_skills:
        profile_skills = detect_skills_in_text(profile_text, 20)
    matched_skills = [s for s in profile_skills if skill_present(s, normalized_job)]

    job_terms = top_terms(job_text, 30)
    profile_terms = set(tokenize(profile_text))
    term_hits = [t for t in job_terms if t in profile_terms]
    term_coverage = min(1.0, len(term_hits) / max(1, min(18, len(job_terms))))

    skill_component = min(1.0, len(matched_skills) / 5) if profile_skills else 0.0
    title_component = _title_score(profile, title) if (profile.get("headline") or (profile.get("preferences") or {}).get("titles")) else 0.0
    score = int(round(100 * (0.6 * skill_component + 0.25 * title_component + 0.15 * term_coverage)))

    preferences = profile.get("preferences") or {}
    desired_locations = split_list(preferences.get("locations", ""))
    if desired_locations and location:
        if any(normalize(loc) in normalize(location) or normalize(location) in normalize(loc) for loc in desired_locations):
            score = min(100, score + 4)

    pref_notes = []
    desired_modes = [m for m in preferences.get("work_modes", []) or [] if m in WORK_MODES]
    desired_types = [t for t in preferences.get("employment_types", []) or [] if t in EMPLOYMENT_TYPES]
    if desired_modes and traits["work_mode"]:
        if traits["work_mode"] in desired_modes:
            score = min(100, score + 5)
            pref_notes.append(f"شیوه همکاری ({WORK_MODES[traits['work_mode']]}) مطابق ترجیح شماست")
        else:
            score = max(0, score - 8)
            pref_notes.append(f"شیوه همکاری ({WORK_MODES[traits['work_mode']]}) با ترجیح شما فرق دارد")
    if desired_types and traits["employment_type"]:
        if traits["employment_type"] in desired_types:
            score = min(100, score + 4)
            pref_notes.append(f"نوع همکاری ({EMPLOYMENT_TYPES[traits['employment_type']]}) مطابق ترجیح شماست")
        else:
            score = max(0, score - 6)
            pref_notes.append(f"نوع همکاری ({EMPLOYMENT_TYPES[traits['employment_type']]}) با ترجیح شما فرق دارد")

    missing_candidates = []
    for skill in detect_skills_in_text(job_text, 30):
        if not any(normalize(skill) == normalize(have) for have in profile_skills):
            missing_candidates.append(skill)
    for term in job_terms:
        if term not in profile_tokens and term not in [normalize(x) for x in missing_candidates]:
            missing_candidates.append(term)
    missing = []
    seen = set()
    for item in missing_candidates:
        key = normalize(item)
        if key and key not in seen:
            seen.add(key)
            missing.append(item)
        if len(missing) >= 10:
            break

    notes = f"{len(matched_skills)} مهارت مشترک · پوشش کلیدواژه {int(term_coverage * 100)}٪"
    if pref_notes:
        notes += " · " + " · ".join(pref_notes)
    return {
        "score": max(0, min(100, score)),
        "matched_skills": matched_skills[:12],
        "missing_keywords": missing,
        "match_notes": notes,
        "work_mode": traits["work_mode"],
        "employment_type": traits["employment_type"],
    }


def profile_completeness(profile, document_count=0):
    checks = [
        ("نام و نام خانوادگی", bool(profile.get("full_name"))),
        ("عنوان شغلی", bool(profile.get("headline"))),
        ("ایمیل", bool(profile.get("email"))),
        ("شماره تماس", bool(profile.get("phone"))),
        ("خلاصه حرفه‌ای", len(profile.get("summary", "")) >= 40),
        ("مهارت‌ها", bool(split_list(profile.get("skills", "")))),
        ("تجربه کاری", bool(profile.get("experiences"))),
        ("تحصیلات", bool(profile.get("education"))),
        ("مدارک", document_count > 0),
        ("عنوان‌های شغلی موردنظر", bool(split_list((profile.get("preferences") or {}).get("titles", "")))),
    ]
    done = sum(1 for _, ok in checks if ok)
    missing = [label for label, ok in checks if not ok]
    return {
        "percent": int(round(done / len(checks) * 100)),
        "done": done,
        "total": len(checks),
        "missing": missing,
        "checks": checks,
    }


def format_jalali(value, with_time=False):
    if not value:
        return "—"
    try:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            parsed = value
        local = parsed.astimezone()
        jalali = jdatetime.date.fromgregorian(date=local.date())
        text = f"{jalali.day} {JALALI_MONTHS[jalali.month - 1]} {jalali.year}"
        if with_time:
            text += f"، {local.hour:02d}:{local.minute:02d}"
        return fa_digits(text)
    except (ValueError, TypeError, OverflowError):
        return "—"


def fa_digits(value):
    return str(value).translate(PERSIAN_DIGITS)


def human_size(size):
    try:
        size = float(size)
    except (TypeError, ValueError):
        return "—"
    for unit in ("بایت", "کیلوبایت", "مگابایت", "گیگابایت"):
        if size < 1024 or unit == "گیگابایت":
            return f"{fa_digits(f'{size:.0f}')} {unit}" if unit == "بایت" else f"{fa_digits(f'{size:.1f}')} {unit}"
        size /= 1024
    return "—"


def truncate(text, limit=160):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def summarize_job_text(text, limit=5000):
    text = re.sub(r"\r", "", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit]


def build_search_links(query, location="", work_modes=None, employment_types=None):
    modes = [m for m in (work_modes or []) if m in WORK_MODES]
    types = [t for t in (employment_types or []) if t in EMPLOYMENT_TYPES]
    base_query = (query or "").strip()
    query_parts = [base_query]
    if len(modes) == 1 and modes[0] in ("remote", "hybrid"):
        query_parts.append(WORK_MODES[modes[0]])
    if len(types) == 1 and types[0] in ("part_time", "contract", "freelance", "internship"):
        query_parts.append(EMPLOYMENT_TYPES[types[0]].replace(" / ", " "))
    fa_q = quote_plus(" ".join(part for part in query_parts if part))
    q = quote_plus(base_query)
    city_slug = "tehran" if "تهران" in (location or "") else "iran"
    linkedin_params = ""
    if modes:
        codes = ",".join(LINKEDIN_WORK_MODE[m] for m in modes)
        linkedin_params += f"&f_WT={quote_plus(codes)}"
    if types:
        codes = ",".join(dict.fromkeys(LINKEDIN_JOB_TYPE[t] for t in types))
        linkedin_params += f"&f_JT={quote_plus(codes)}"
    return [
        {"name": "جابینجا", "url": f"https://jobinja.ir/jobs?filters%5Bkeywords%5D%5B0%5D={fa_q}",
         "note": "بازار آگهی‌های تخصصی ایران"},
        {"name": "جاب‌ویژن", "url": f"https://jobvision.ir/jobs?keyword={fa_q}",
         "note": "جستجوی سریع بر اساس عنوان"},
        {"name": "ای‌استخدام", "url": f"https://e-estekhdam.com/search?q={fa_q}",
         "note": "آگهی‌های عمومی و اداری"},
        {"name": "دیوار", "url": f"https://divar.ir/s/{city_slug}/jobs?q={fa_q}",
         "note": "فرصت‌های محلی و سریع"},
        {"name": "لینکدین", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&location=Iran{linkedin_params}",
         "note": "موقعیت‌های بین‌المللی و ریموت"},
    ]


def clean_html_text(html):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()
        text = soup.get_text("\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html or "").strip()
