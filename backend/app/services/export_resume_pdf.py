"""ATS-friendly PDF export of a tailored resume (reportlab).

What makes the output ATS-safe, and why every template here follows it:
  * ONE column, top-to-bottom reading order - parsers read columns/tables in the wrong order.
  * Real text in a standard font (Helvetica / Times), never an image, so it is selectable and parseable.
  * Conventional section headings (SUMMARY, SKILLS, EXPERIENCE, PROJECTS, EDUCATION, AWARDS) that
    parsers look for. No icons, graphics, text boxes, headers/footers, or tables.
  * Plain bullets ("•"), plain "·"/"|" separators, dates inline with the role.
  * PDF title/author metadata set so the file shows the candidate's name.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer


@dataclass(frozen=True)
class Template:
    key: str
    label: str
    description: str
    font: str
    bold: str
    body: float
    name_size: float
    head_size: float
    leading: float
    margin_mm: float
    section_gap: float
    rule: bool                 # thin black line under each section heading
    align: str = "left"        # name + contact line: "left" | "center"
    accent: str = "#000000"    # colour of the name and section headings (body text is always black)
    head_bar: bool = False     # shaded bar behind section headings instead of a line
    bar_color: str = "#EEF1F5"


# All three are ATS-safe: single column, real text, standard headings. They differ in look only.
TEMPLATES: dict[str, Template] = {
    "ats_classic": Template(
        key="ats_classic", label="ATS Classic",
        description="Helvetica, black, left-aligned with a rule under each heading. The safest choice for almost every ATS.",
        font="Helvetica", bold="Helvetica-Bold", body=10, name_size=20, head_size=10.5, leading=13.2,
        margin_mm=18, section_gap=10, rule=True),
    "ats_compact": Template(
        key="ats_compact", label="ATS Compact",
        description="Dense layout with navy name and shaded section bars. Fits the most on one page.",
        font="Helvetica", bold="Helvetica-Bold", body=9.2, name_size=18, head_size=9.5, leading=11.6,
        margin_mm=14, section_gap=7, rule=False, accent="#1F3A5F", head_bar=True),
    "ats_serif": Template(
        key="ats_serif", label="ATS Serif",
        description="Traditional Times look with a centered name and contact line. Formal and spacious.",
        font="Times-Roman", bold="Times-Bold", body=10.5, name_size=22, head_size=11, leading=13.6,
        margin_mm=20, section_gap=11, rule=True, align="center"),
}
DEFAULT_TEMPLATE = "ats_classic"

_PAGES = {"a4": A4, "letter": LETTER}
_BULLET_RE = re.compile(r"^\s*(?:[-*•▪◦●–—]|\d+[.)])\s+")

_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2026": "...", "\u00a0": " ", "\u2022": "•", "\u25aa": "•", "\u25e6": "•", "\u25cf": "•", "\u2192": "->",
    "\u20b9": "Rs. ", "\u200b": "", "\ufeff": "", "\t": " ",
}


def _clean(s: Any) -> str:
    """Standard PDF fonts only cover Latin-1: map common punctuation, strip what cannot be drawn."""
    out = []
    for ch in str(s or ""):
        ch = _MAP.get(ch, ch)
        for c in ch:
            try:
                c.encode("latin-1")
                out.append(c)
            except UnicodeEncodeError:
                base = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
                out.append(base)
    return "".join(out)


def _esc(s: Any) -> str:
    return _clean(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles(t: Template) -> dict[str, ParagraphStyle]:
    black = colors.black
    accent = colors.HexColor(t.accent)
    al = TA_CENTER if t.align == "center" else TA_LEFT
    head = dict(fontName=t.bold, fontSize=t.head_size, leading=t.head_size * 1.25, textColor=accent,
                spaceBefore=t.section_gap, spaceAfter=2)
    if t.head_bar:
        # shaded bar spanning exactly the text width; the heading is still ordinary text
        head.update(backColor=colors.HexColor(t.bar_color), borderPadding=(2, 3, 2, 3), leftIndent=3, rightIndent=3,
                    spaceBefore=t.section_gap + 3, spaceAfter=5)
    return {
        "name": ParagraphStyle("name", fontName=t.bold, fontSize=t.name_size, leading=t.name_size * 1.2,
                               textColor=accent, alignment=al, spaceAfter=2),
        "contact": ParagraphStyle("contact", fontName=t.font, fontSize=t.body - 0.5, leading=t.leading,
                                  textColor=colors.HexColor("#333333"), alignment=al, spaceAfter=2),
        "head": ParagraphStyle("head", **head),
        "title": ParagraphStyle("title", fontName=t.bold, fontSize=t.body + 0.5, leading=t.leading,
                                textColor=black, spaceBefore=4),
        "sub": ParagraphStyle("sub", fontName=t.font, fontSize=t.body - 0.5, leading=t.leading,
                              textColor=colors.HexColor("#333333")),
        "body": ParagraphStyle("body", fontName=t.font, fontSize=t.body, leading=t.leading, textColor=black),
        "bullet": ParagraphStyle("bullet", fontName=t.font, fontSize=t.body, leading=t.leading, textColor=black,
                                 leftIndent=12, bulletIndent=2, spaceAfter=1),
    }


def _content_flowables(content: str, st: dict[str, ParagraphStyle]) -> list:
    out: list = []
    for line in str(content or "").splitlines():
        if not line.strip():
            continue
        if _BULLET_RE.match(line):
            out.append(Paragraph(_esc(_BULLET_RE.sub("", line)), st["bullet"], bulletText="•"))
        else:
            out.append(Paragraph(_esc(line.strip()), st["body"]))
    return out


def _section(heading: str, items: list, st: dict[str, ParagraphStyle], t: Template) -> list:
    if not items:
        return []
    head: list = [Paragraph(_esc(heading.upper()), st["head"])]
    if t.rule and not t.head_bar:
        head.append(HRFlowable(width="100%", thickness=0.6, color=colors.black, spaceBefore=0, spaceAfter=3))
    return head + items


def render_resume_pdf(resume: dict[str, Any], *, template: str = DEFAULT_TEMPLATE, page: str = "a4") -> bytes:
    t = TEMPLATES.get(template) or TEMPLATES[DEFAULT_TEMPLATE]
    st = _styles(t)
    p = resume.get("profile") or {}
    name = _clean(p.get("name") or "").strip() or "Candidate"

    story: list = [Paragraph(_esc(name), st["name"])]
    contact = [p.get("email"), p.get("phone"), p.get("city"), p.get("github")]
    contact_line = "  |  ".join(_esc(c) for c in contact if c and str(c).strip())
    if contact_line:
        story.append(Paragraph(contact_line, st["contact"]))

    if str(resume.get("summary") or "").strip():
        story += _section("Summary", [Paragraph(_esc(resume["summary"]), st["body"])], st, t)

    skills = [str(s).strip() for s in resume.get("skills") or [] if str(s).strip()]
    if skills:
        story += _section("Skills", [Paragraph(_esc(", ".join(skills)), st["body"])], st, t)

    def entries(key: str) -> list:
        flow: list = []
        for it in resume.get(key) or []:
            if isinstance(it, dict):
                title = it.get("title") or ""
                block = ([Paragraph(_esc(title), st["title"])] if title else []) + _content_flowables(it.get("content"), st)
            else:
                block = _content_flowables(str(it), st)
            if block:
                # keep a role title with its first line so it never sits alone at a page bottom
                flow.append(KeepTogether(block[:2]))
                flow.extend(block[2:])
                flow.append(Spacer(1, 3))
        return flow

    story += _section("Experience", entries("experience"), st, t)
    story += _section("Projects", entries("projects"), st, t)

    edu: list = []
    for ed in resume.get("education") or []:
        if not isinstance(ed, dict):
            continue
        school = ed.get("school") or ""
        degree = " ".join(x for x in [ed.get("degree"), ed.get("major")] if x)
        dates = " - ".join(x for x in [ed.get("start_date"), ed.get("end_date")] if x)
        line1 = _esc(school)
        line2 = _esc(", ".join(x for x in [degree, dates] if x))
        block = []
        if school:
            block.append(Paragraph(line1, st["title"]))
        if line2:
            block.append(Paragraph(line2, st["sub"]))
        if block:
            edu.append(KeepTogether(block))
    story += _section("Education", edu, st, t)
    story += _section("Awards", entries("awards"), st, t)

    buf = io.BytesIO()
    m = t.margin_mm * mm
    doc = SimpleDocTemplate(
        buf, pagesize=_PAGES.get(page, A4), leftMargin=m, rightMargin=m, topMargin=m * 0.9, bottomMargin=m * 0.9,
        title=f"{name} - Resume", author=name, subject="Resume", creator="CareerPrep",
    )
    doc.build(story)
    return buf.getvalue()
