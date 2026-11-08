from datetime import datetime
import os
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, HRFlowable, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

from utils import fa_digits, format_jalali, split_list

ROOT_DIR = Path(os.environ.get("RESUMEYAR_ROOT") or Path(__file__).resolve().parent.parent)
FONT_DIR = ROOT_DIR / "static" / "fonts"
FONT_REGULAR = "Vazirmatn"
FONT_BOLD = "Vazirmatn-Bold"

NAVY = colors.HexColor("#102a43")
GOLD = colors.HexColor("#b08d3f")
INK = colors.HexColor("#263442")
MUTED = colors.HexColor("#66737f")
LINE = colors.HexColor("#ddd5c5")

PAGE_W, PAGE_H = A4
MARGIN_X = 17 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X
COVER_MARGIN_X = 20 * mm
COVER_W = PAGE_W - 2 * COVER_MARGIN_X


def _register_fonts():
    registered = pdfmetrics.getRegisteredFontNames()
    if FONT_REGULAR not in registered:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_DIR / "Vazirmatn-Regular.ttf")))
    if FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "Vazirmatn-Bold.ttf")))


_register_fonts()


def shape(value, language):
    text = str(value or "").strip()
    if not text:
        return ""
    if language == "fa":
        return get_display(arabic_reshaper.reshape(text), base_dir="R")
    return text


def _escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _styles(language):
    align = TA_RIGHT if language == "fa" else TA_LEFT
    bullet_align = TA_RIGHT if language == "fa" else TA_LEFT
    return {
        "name": ParagraphStyle("name", fontName=FONT_BOLD, fontSize=22, leading=28,
                               textColor=NAVY, alignment=align, spaceAfter=2),
        "headline": ParagraphStyle("headline", fontName=FONT_BOLD, fontSize=11, leading=16,
                                   textColor=GOLD, alignment=align, spaceAfter=3),
        "contact": ParagraphStyle("contact", fontName=FONT_REGULAR, fontSize=8.6, leading=13,
                                  textColor=MUTED, alignment=align, splitLongWords=1),
        "section": ParagraphStyle("section", fontName=FONT_BOLD, fontSize=12, leading=17,
                                  textColor=NAVY, alignment=align, spaceBefore=2),
        "body": ParagraphStyle("body", fontName=FONT_REGULAR, fontSize=9.8, leading=16.6,
                               textColor=INK, alignment=align),
        "bullet": ParagraphStyle("bullet", fontName=FONT_REGULAR, fontSize=9.8, leading=16.4,
                                 textColor=INK, alignment=align, firstLineIndent=0),
        "bullet_marker": ParagraphStyle("bullet_marker", fontName=FONT_REGULAR, fontSize=10.4,
                                        leading=16.4, textColor=INK, alignment=bullet_align),
        "subhead": ParagraphStyle("subhead", fontName=FONT_BOLD, fontSize=10.4, leading=15,
                                  textColor=INK, alignment=align),
        "meta": ParagraphStyle("meta", fontName=FONT_REGULAR, fontSize=8.6, leading=13,
                               textColor=MUTED, alignment=align),
        "date": ParagraphStyle("date", fontName=FONT_REGULAR, fontSize=8.6, leading=13,
                               textColor=MUTED,
                               alignment=TA_LEFT if language == "fa" else TA_RIGHT),
        "letter": ParagraphStyle("letter", fontName=FONT_REGULAR, fontSize=10.2, leading=18,
                                 textColor=INK, alignment=align, spaceAfter=9),
        "letter_subject": ParagraphStyle("letter_subject", fontName=FONT_BOLD, fontSize=11,
                                         leading=17, textColor=NAVY, alignment=align, spaceAfter=10),
        "small": ParagraphStyle("small", fontName=FONT_REGULAR, fontSize=8.4, leading=12,
                                textColor=MUTED, alignment=align),
    }


def _shape_line(text):
    return get_display(arabic_reshaper.reshape(str(text)), base_dir="R")


def _bidi_line(text):
    """Bidi for LTR paragraphs that may embed Persian words."""
    return get_display(arabic_reshaper.reshape(str(text)), base_dir="L")


def _direction(text):
    """Return 'R' when most letters are Persian, otherwise 'L'."""
    letters = [char for char in str(text or "") if char.isalpha()]
    if not letters:
        return "L"
    persian = sum(1 for char in letters if "\u0600" <= char <= "\u06ff")
    return "R" if persian * 2 > len(letters) else "L"


def _rtl_lines(text, font_name, font_size, max_width):
    """Greedy-wrap logical RTL text, so each physical line keeps its order after bidi."""
    lines = []
    space_width = pdfmetrics.stringWidth(" ", font_name, font_size)
    for raw_line in str(text).split("\n"):
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current, current_width = [], 0.0
        for word in words:
            word_width = pdfmetrics.stringWidth(_shape_line(word), font_name, font_size)
            needed = word_width + (space_width if current else 0)
            if current and current_width + needed > max_width:
                lines.append(" ".join(current))
                current, current_width = [word], word_width
            else:
                current.append(word)
                current_width += needed
        if current:
            lines.append(" ".join(current))
    return lines


def _text_markup(value, style, language, width):
    text = str(value or "").strip()
    if not text:
        return ""
    if language == "fa":
        lines = _rtl_lines(text, style.fontName, style.fontSize, width)
        return "<br/>".join(_escape(_shape_line(line)) for line in lines)
    lines = [_bidi_line(line) for line in text.split("\n")]
    return "<br/>".join(_escape(line) for line in lines)


def _para(text, style, language, width=CONTENT_W):
    value = str(text or "").strip()
    if not value:
        return Paragraph("", style)
    if language == "fa" and style.alignment != TA_RIGHT:
        style = ParagraphStyle(style.name + "-rtl", parent=style, alignment=TA_RIGHT)
    elif language != "fa" and _direction(value) == "R":
        style = ParagraphStyle(style.name + "-rtl", parent=style, alignment=TA_RIGHT)
        language = "fa"
    return Paragraph(_text_markup(value, style, language, width), style)


def _contact_markup(profile, language):
    """Shape each contact item on its own, so phone/URL runs never get reordered."""
    items = [
        profile.get("phone", "").strip(),
        profile.get("email", "").strip(),
        profile.get("city", "").strip(),
        " ".join(profile.get("links", "").replace("\n", " ").split()),
    ]
    rendered = []
    for item in items:
        if not item:
            continue
        if _direction(item) == "R":
            item = _shape_line(item)
        rendered.append(_escape(item))
    if language == "fa":
        rendered.reverse()
    return "   ·   ".join(rendered)


def _header(story, profile, job, styles, language, width=CONTENT_W):
    name = profile.get("full_name", "").strip()
    if not name:
        name = "رزومه" if language == "fa" else "Resume"
    story.append(_para(name, styles["name"], language, width))
    headline = (job or {}).get("headline") or profile.get("headline", "")
    if headline:
        story.append(_para(headline, styles["headline"], language, width))
    contact_line = _contact_markup(profile, language)
    if contact_line:
        story.append(Spacer(1, 2))
        story.append(Paragraph(contact_line, styles["contact"]))
    story.append(Spacer(1, 5))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD,
                            spaceBefore=0, spaceAfter=1.5))
    story.append(HRFlowable(width="100%", thickness=0.4, color=LINE,
                            spaceBefore=0, spaceAfter=9))


def _section(story, title, styles, language):
    story.append(CondPageBreak(58))
    story.append(Spacer(1, 7))
    story.append(_para(title, styles["section"], language))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE,
                            spaceBefore=2, spaceAfter=7))


def _two_col(left_text, right_text, left_style, right_style, language):
    date_width = 42 * mm
    if language == "fa":
        col_widths = [date_width, CONTENT_W - date_width]
    else:
        col_widths = [CONTENT_W - date_width, date_width]
    left_para = _para(left_text, left_style, language, col_widths[0])
    right_para = _para(right_text, right_style, language, col_widths[1])
    table = Table([[left_para, right_para]], colWidths=col_widths)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _bullet_row(text, styles, language):
    marker_width = 5 * mm
    text_width = CONTENT_W - marker_width
    row_language = "fa" if _direction(text) == "R" else "en"
    marker_style = styles["bullet_marker"]
    if (row_language == "fa") != (language == "fa"):
        marker_style = ParagraphStyle(
            "bullet_marker-row", parent=marker_style,
            alignment=TA_RIGHT if row_language == "fa" else TA_LEFT,
        )
    marker = Paragraph("•", marker_style)
    body = _para(text, styles["bullet"], row_language, text_width)
    if row_language == "fa":
        cells, widths = [[body, marker]], [text_width, marker_width]
    else:
        cells, widths = [[marker, body]], [marker_width, text_width]
    table = Table(cells, colWidths=widths)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _date_range(start, end):
    start, end = str(start or "").strip(), str(end or "").strip()
    if start and end:
        return f"{start} – {end}"
    return start or end


def _render_education(story, profile, styles, language):
    education = profile.get("education") or []
    if not education:
        return
    _section(story, "تحصیلات" if language == "fa" else "Education", styles, language)
    for item in education:
        if not isinstance(item, dict):
            continue
        degree = item.get("degree", "").strip()
        field = item.get("field", "").strip()
        school = item.get("school", "").strip()
        title = " | ".join(x for x in (degree, field) if x) or school
        if not title:
            continue
        dates = _date_range(item.get("start"), item.get("end"))
        row_language = "fa" if _direction(title) == "R" else "en"
        if row_language == "fa":
            row = _two_col(dates, title, styles["date"], styles["subhead"], row_language)
        else:
            row = _two_col(title, dates, styles["subhead"], styles["date"], row_language)
        story.append(row)
        if school and school != title:
            story.append(Spacer(1, 1))
            story.append(_para(school, styles["meta"], language))
        story.append(Spacer(1, 7))


def _render_experiences(story, profile, styles, language):
    experiences = profile.get("experiences") or []
    if not experiences:
        return
    _section(story, "تجربه کاری" if language == "fa" else "Experience", styles, language)
    for item in experiences:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "").strip()
        company = item.get("company", "").strip()
        location = item.get("location", "").strip()
        if not (title or company):
            continue
        dates = _date_range(item.get("start"), item.get("end"))
        row_language = "fa" if _direction(title) == "R" else "en"
        title = " | ".join(x for x in (title, company) if x)
        if dates:
            if row_language == "fa":
                story.append(_two_col(dates, title, styles["date"], styles["subhead"], row_language))
            else:
                story.append(_two_col(title, dates, styles["subhead"], styles["date"], row_language))
        else:
            story.append(_para(title, styles["subhead"], row_language))
        if location:
            story.append(_para(location, styles["meta"], language))
        bullets = [_clean_bullet(b) for b in (item.get("bullets") or []) if _clean_bullet(b)]
        if bullets:
            story.append(Spacer(1, 2))
            for bullet in bullets:
                story.append(_bullet_row(bullet, styles, language))
        story.append(Spacer(1, 8))


def _clean_bullet(text):
    import re
    return re.sub(r"^[\s•●▪\-–—*]+", "", str(text or "")).strip()


def _render_languages(story, profile, styles, language):
    languages = split_list(profile.get("languages", ""))
    if not languages:
        return
    _section(story, "زبان‌ها" if language == "fa" else "Languages", styles, language)
    story.append(_para("  ·  ".join(languages), styles["body"], language))


def _footer_factory(language):
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 8)
        canvas.setFillColor(MUTED)
        label = f"صفحه {fa_digits(doc.page)}" if language == "fa" else f"Page {doc.page}"
        canvas.drawCentredString(PAGE_W / 2, 9 * mm, shape(label, language))
        canvas.restoreState()
    return footer


def _document(path, margin_x, title, author, language):
    doc = BaseDocTemplate(
        str(path), pagesize=A4, leftMargin=margin_x, rightMargin=margin_x,
        topMargin=15 * mm, bottomMargin=18 * mm, title=title, author=author,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=_footer_factory(language))])
    return doc


def build_cv_pdf(path, profile, tailored, language="fa", job=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _document(path, MARGIN_X, "Resume",
                    profile.get("full_name", "") or "Resume", language)
    styles = _styles(language)
    story = []
    _header(story, profile, {"headline": tailored.get("headline") or profile.get("headline", "")},
            styles, language)

    summary = (tailored.get("summary") or "").strip()
    if summary:
        _section(story, "خلاصه حرفه‌ای" if language == "fa" else "Professional Summary",
                 styles, language)
        story.append(_para(summary, styles["body"], language))

    skills = tailored.get("skills") or split_list(profile.get("skills", ""))
    skills = [str(s).strip() for s in skills if str(s).strip()]
    if skills:
        _section(story, "مهارت‌ها" if language == "fa" else "Skills", styles, language)
        story.append(_para("  ·  ".join(skills[:30]), styles["body"], language))

    _render_experiences(story, profile, styles, language)
    _render_education(story, profile, styles, language)
    _render_languages(story, profile, styles, language)

    doc.build(story)
    return path


def _letter_blocks(text, style, language, width=COVER_W):
    blocks = [b.strip("\n") for b in str(text or "").split("\n\n") if b.strip()]
    flowables = []
    for block in blocks:
        flowables.append(_para(block, style, language, width))
    return flowables


def build_cover_pdf(path, profile, job, cover_letter, language="fa"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _document(path, COVER_MARGIN_X, "Cover Letter",
                    profile.get("full_name", "") or "Cover Letter", language)
    styles = _styles(language)
    story = []
    _header(story, profile, None, styles, language, COVER_W)

    story.append(Spacer(1, 6))
    date_text = format_jalali(datetime.now().isoformat()) if language == "fa" \
        else datetime.now().strftime("%B %d, %Y")
    story.append(_para(date_text, styles["small"], language, COVER_W))
    story.append(Spacer(1, 10))

    company = job.get("company", "").strip()
    location = job.get("location", "").strip()
    recipient = company
    if company and location:
        recipient = f"{company} — {location}"
    if recipient:
        story.append(_para(recipient, styles["body"], language, COVER_W))
        story.append(Spacer(1, 8))

    title = job.get("title", "").strip()
    if title:
        subject = f"موضوع: درخواست همکاری برای موقعیت {title}" if language == "fa" \
            else f"Subject: Application for {title}"
        story.append(_para(subject, styles["letter_subject"], language, COVER_W))

    story.extend(_letter_blocks(cover_letter, styles["letter"], language, COVER_W))

    doc.build(story)
    return path
