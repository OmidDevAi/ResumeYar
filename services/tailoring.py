import re

from utils import normalize, skill_present, split_list


def _clean_bullet(text):
    return re.sub(r"^[\s•●▪\-–—*]+", "", str(text or "")).strip()


def _is_persian(text):
    return bool(re.search(r"[\u0600-\u06ff]", str(text or "")))


def _ordered_skills(profile, job_text):
    skills = split_list(profile.get("skills", ""))
    normalized_job = normalize(job_text)
    matched = [s for s in skills if skill_present(s, normalized_job)]
    rest = [s for s in skills if s not in matched]
    ordered = matched + rest
    return ordered[:24] if len(ordered) > 24 else ordered, matched


def _first_experience(profile):
    experiences = profile.get("experiences") or []
    if experiences and isinstance(experiences[0], dict):
        return experiences[0]
    return {}


def _join_fa(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "، ".join(items[:-1]) + " و " + items[-1]


def _join_en(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def local_summary(profile, job, skills, matched, language):
    title = job.get("title", "").strip() or ("موقعیت موردنظر" if language == "fa" else "the advertised role")
    company = job.get("company", "").strip()
    headline = profile.get("headline", "").strip()
    experience = _first_experience(profile)
    exp_title = experience.get("title", "").strip()
    exp_company = experience.get("company", "").strip()
    focus = (matched or skills)[:5]

    if language == "fa":
        intro = headline or "متخصص"
        if exp_title:
            intro += f" با تجربه در نقش {exp_title}"
            if exp_company:
                intro += f" در {exp_company}"
            if focus:
                intro += f" و تسلط بر {_join_fa(focus[:4])}"
            intro += "."
        elif focus:
            intro += f" با مهارت در {_join_fa(focus[:4])}."
        target = f"آماده همکاری در موقعیت «{title}»"
        if company:
            target += f" در {company}"
        if focus:
            target += f" با تمرکز بر {_join_fa(focus[:3])}"
        target += " است."
        return f"{intro} {target}"

    intro = headline or "Professional"
    if exp_title:
        intro += f" with experience as {exp_title}"
        if exp_company:
            intro += f" at {exp_company}"
        if focus:
            intro += f" and strengths in {_join_en(focus[:4])}"
        intro += "."
    elif focus:
        intro += f" with strengths in {_join_en(focus[:4])}."
    target = f"Seeking to contribute to the {title} role"
    if company:
        target += f" at {company}"
    if focus:
        target += f", focusing on {_join_en(focus[:3])}"
    target += "."
    return f"{intro} {target}"


def local_cover_letter(profile, job, skills, matched, language):
    name = profile.get("full_name", "").strip()
    headline = profile.get("headline", "").strip()
    title = job.get("title", "").strip() or ("موقعیت موردنظر" if language == "fa" else "the advertised role")
    company = job.get("company", "").strip()
    contact = " | ".join(x for x in (profile.get("phone", ""), profile.get("email", "")) if x)
    experience = _first_experience(profile)
    bullets = [_clean_bullet(b) for b in (experience.get("bullets") or []) if _clean_bullet(b)]
    proof = bullets[0] if bullets else ""
    focus = (matched or skills)[:5]

    if language == "fa":
        if company:
            greeting = f"با سلام و احترام،\n\nدرخواست همکاری خود را برای موقعیت «{title}» در {company} ارسال می‌کنم."
        else:
            greeting = f"با سلام و احترام،\n\nدرخواست همکاری خود را برای موقعیت «{title}» ارسال می‌کنم."
        if headline:
            greeting += f" {headline} هستم"
            greeting += f" و در {_join_fa(focus[:4])} تجربه و تسلط دارم." if focus else "."
        elif focus:
            greeting += f" در {_join_fa(focus[:4])} تجربه و تسلط دارم."

        body_parts = []
        if experience.get("title"):
            line = f"در تجربه کاری خود به عنوان {experience['title']}"
            if experience.get("company"):
                line += f" در {experience['company']}"
            line += "،"
            if proof:
                line += f" مسئول {proof.rstrip('.')} بوده‌ام."
            elif focus:
                line += f" بر {_join_fa(focus[:3])} تمرکز داشته‌ام."
            else:
                line += " با استانداردهای حرفه‌ای کار تیمی و پیگیری منظم آشنا شده‌ام."
            body_parts.append(line)
        if focus:
            body_parts.append(
                f"مهارت‌های من در {_join_fa(focus[:4])} با نیازهای این نقش هم‌راستا است و می‌توانم در "
                "پیشبرد وظایف و ارائه گزارش‌های دقیق نقش مؤثری داشته باشم."
            )
        body_parts.append(
            "رزومه تنظیم‌شده و مدارک مرتبط را به این درخواست پیوست کرده‌ام و برای گفت‌وگو درباره "
            "نحوه همکاری در دسترس هستم."
        )
        closing = "با احترام"
        signature = f"{closing}،\n{name}" if name else closing
        if contact:
            signature += f"\n{contact}"
        return greeting + "\n\n" + "\n\n".join(body_parts) + "\n\n" + signature

    greeting = f"Dear {company + ' ' if company else ''}Hiring Team,\n\n"
    greeting += f"I am writing to apply for the {title} position"
    greeting += f" at {company}." if company else "."
    if headline:
        greeting += f" I am a {headline}"
        greeting += f" with experience in {_join_en(focus[:4])}." if focus else "."
    elif focus:
        greeting += f" I have experience in {_join_en(focus[:4])}."

    body_parts = []
    if experience.get("title"):
        line = f"In my role as {experience['title']}"
        if experience.get("company"):
            line += f" at {experience['company']}"
        line += ","
        if proof and not _is_persian(proof):
            line += f" I {proof[0].lower() + proof[1:]}" if proof[:1].isupper() else f" {proof}"
            if not line.rstrip().endswith((".", "!", "?")):
                line += "."
        elif focus:
            line += f" I focused on {_join_en(focus[:3])}."
        else:
            line += " I built strong habits in teamwork and dependable follow-through."
        body_parts.append(line)
    if focus:
        body_parts.append(
            f"My background in {_join_en(focus[:4])} aligns with the needs of this role, and I am "
            "confident I can contribute to clear reporting and reliable execution."
        )
    body_parts.append(
        "My tailored CV and supporting documents are attached. I would welcome the opportunity "
        "to discuss how my experience can support your team."
    )
    signature = "Sincerely"
    if name:
        signature += f",\n{name}"
    if contact:
        signature += f"\n{contact}"
    return greeting + "\n\n" + "\n\n".join(body_parts) + "\n\n" + signature


def local_tailor(profile, job, language):
    job_text = f"{job.get('title', '')} {job.get('description', '')}"
    skills, matched = _ordered_skills(profile, job_text)
    if not skills:
        skills = []
    return {
        "headline": profile.get("headline", "").strip(),
        "summary": local_summary(profile, job, skills, matched, language),
        "skills": skills,
        "cover_letter": local_cover_letter(profile, job, skills, matched, language),
        "mode": "local",
    }


def email_draft(profile, job, language):
    name = profile.get("full_name", "").strip()
    title = job.get("title", "").strip() or ("موقعیت موردنظر" if language == "fa" else "the advertised role")
    company = job.get("company", "").strip()
    contact = " | ".join(x for x in (profile.get("phone", ""), profile.get("email", "")) if x)

    if language == "fa":
        subject = f"درخواست همکاری: {title}"
        if name:
            subject += f" — {name}"
        if company:
            body = f"سلام {company}،\n\n"
        else:
            body = "سلام،\n\n"
        body += (
            f"درخواست همکاری من برای موقعیت «{title}» به همراه رزومه تنظیم‌شده، "
            "نامه انگیزه و مدارک مرتبط پیوست است.\n\n"
            "برای هماهنگی مصاحبه یا ارائه توضیحات بیشتر در دسترس هستم.\n\n"
        )
        body += f"با احترام،\n{name}" if name else "با احترام"
        if contact:
            body += f"\n{contact}"
        return {"subject": subject, "body": body}

    subject = f"Application for {title}"
    if name:
        subject += f" — {name}"
    body = f"Dear {company + ' ' if company else ''}Hiring Team,\n\n"
    body += (
        f"Please find attached my tailored CV, cover letter, and supporting documents for the "
        f"{title} position.\n\n"
        "I would be glad to provide any additional information or arrange a conversation.\n\n"
    )
    body += f"Sincerely,\n{name}" if name else "Sincerely"
    if contact:
        body += f"\n{contact}"
    return {"subject": subject, "body": body}
