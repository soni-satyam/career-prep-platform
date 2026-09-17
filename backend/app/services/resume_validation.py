"""Re-open a generated resume file and check it the way an ATS parser would see it.

Each check returns status "pass" | "warn" | "fail". The file is acceptable when nothing fails;
warnings (e.g. a 3-page resume) are shown to the user but do not block download.
"""

from __future__ import annotations

import io
import re
from typing import Any

from app.services.export_resume_pdf import _clean

_STANDARD_FONTS = ("helvetica", "arial", "times", "courier", "symbol", "zapfdingbats")
_HEADINGS = [("summary", "SUMMARY"), ("skills", "SKILLS"), ("experience", "EXPERIENCE"),
             ("projects", "PROJECTS"), ("education", "EDUCATION"), ("awards", "AWARDS")]


def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def _item_text(it: Any) -> str:
    if isinstance(it, dict):
        return " ".join(str(it.get(k) or "") for k in ("title", "content", "school", "degree", "major", "start_date", "end_date"))
    return str(it or "")


def rendered_text(resume: dict[str, Any]) -> str:
    """Everything the exporters actually print (and nothing they don't, e.g. profile.school)."""
    p = resume.get("profile") or {}
    parts = [p.get("name"), p.get("email"), p.get("phone"), p.get("city"), p.get("github"), resume.get("summary"),
             " ".join(str(s) for s in resume.get("skills") or [])]
    for key in ("experience", "projects", "education", "awards"):
        parts += [_item_text(it) for it in resume.get(key) or []]
    return " ".join(str(x) for x in parts if x)


def expected_sections(resume: dict[str, Any]) -> list[str]:
    out = []
    for key, label in _HEADINGS:
        v = resume.get(key)
        if key == "summary":
            if str(v or "").strip():
                out.append(label)
        elif key == "skills":
            if any(str(s).strip() for s in v or []):
                out.append(label)
        elif v and any(_item_text(it).strip() for it in v):
            out.append(label)
    return out


def _check(cid: str, label: str, status: str, detail: str = "") -> dict[str, str]:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def _coverage(resume: dict[str, Any], extracted: str, *, clean: bool) -> tuple[float, list[str]]:
    want = set(_tok(_clean(rendered_text(resume)) if clean else rendered_text(resume)))
    if not want:
        return 1.0, []
    have = set(_tok(extracted))
    missing = sorted(want - have)
    return 1 - len(missing) / len(want), missing


def _order_ok(text_upper: str, sections: list[str]) -> tuple[bool, str]:
    pos = []
    for s in sections:
        m = re.search(rf"(?m)^\s*{s}\s*$", text_upper)
        if not m:
            return False, f"Heading “{s.title()}” was not found as its own line"
        pos.append(m.start())
    if pos != sorted(pos):
        return False, "Sections are not in a top-to-bottom order"
    return True, ""


def _contact_check(resume: dict[str, Any], extracted: str) -> dict[str, str]:
    p = resume.get("profile") or {}
    have = set(_tok(extracted))
    missing = [k for k in ("email", "phone") if p.get(k) and not set(_tok(_clean(p[k]))) <= have]
    if not (p.get("email") or p.get("phone")):
        return _check("contact", "Contact details", "warn", "No email or phone on the resume — recruiters need one")
    if missing:
        return _check("contact", "Contact details", "fail", f"Missing from file: {', '.join(missing)}")
    return _check("contact", "Contact details", "pass", "Email and phone are readable text")


def validate_pdf(pdf: bytes, resume: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    pages = None
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf))
        pages = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "pages": None, "checks": [_check("opens", "File opens", "fail", f"Could not read the PDF: {e}")]}

    checks.append(_check("opens", "File opens", "pass" if pages else "fail", f"{pages} page{'s' if pages != 1 else ''}"))

    images = sum(len(list(p.images)) for p in reader.pages)
    selectable = len(text.strip()) >= 40 and images == 0
    checks.append(_check("text", "Text is selectable (not an image)", "pass" if selectable else "fail",
                         "Real text, no images" if selectable else "Little or no extractable text, or images found"))

    fonts: set[str] = set()
    for p in reader.pages:
        res = p.get("/Resources") or {}
        for f in ((res.get("/Font") or {}).values() if hasattr(res.get("/Font") or {}, "values") else []):
            try:
                fonts.add(str(f.get_object().get("/BaseFont", "")).lstrip("/").lower())
            except Exception:  # noqa: BLE001
                pass
    odd = sorted(f for f in fonts if f and not f.startswith(_STANDARD_FONTS))
    checks.append(_check("fonts", "Standard fonts", "pass" if not odd else "warn",
                         "Helvetica / Times only" if not odd else f"Non-standard fonts: {', '.join(odd)}"))

    sections = expected_sections(resume)
    ok, why = _order_ok(text.upper(), sections)
    checks.append(_check("sections", "Standard headings, single-column order", "pass" if ok else "fail",
                         " → ".join(s.title() for s in sections) if ok else why))

    checks.append(_contact_check(resume, text))

    cov, missing = _coverage(resume, text, clean=True)
    checks.append(_check("content", "All your content is in the file", "pass" if cov >= 0.98 else "fail",
                         "Every word from the editor is present" if cov >= 0.98
                         else f"{round((1 - cov) * 100)}% of words are missing, e.g. {', '.join(missing[:5])}"))

    checks.append(_check("length", "Length", "pass" if pages <= 2 else "warn",
                         f"{pages} page{'s' if pages != 1 else ''}" + ("" if pages <= 2 else " — most recruiters prefer 1–2 pages; try ATS Compact")))
    return {"ok": all(c["status"] != "fail" for c in checks), "pages": pages, "checks": checks}


def validate_docx(data: bytes, resume: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "pages": None, "checks": [_check("opens", "File opens", "fail", f"Could not read the DOCX: {e}")]}
    checks.append(_check("opens", "File opens", "pass", "Valid Word document"))

    xml = doc.element.xml
    bad = []
    if doc.tables:
        bad.append("tables")
    if doc.inline_shapes or "<w:drawing" in xml or "<w:pict" in xml:
        bad.append("images/shapes")
    if "w:txbxContent" in xml:
        bad.append("text boxes")
    checks.append(_check("layout", "No tables, images or text boxes", "pass" if not bad else "fail",
                         "Plain paragraphs only" if not bad else f"Found {', '.join(bad)}"))

    cols = doc.sections[0]._sectPr.xpath("./w:cols/@w:num")
    single = not cols or int(cols[0]) <= 1
    checks.append(_check("columns", "Single column", "pass" if single else "fail", "One column" if single else f"{cols[0]} columns"))

    sec = doc.sections[0]
    hf = " ".join(p.text for p in list(sec.header.paragraphs) + list(sec.footer.paragraphs)).strip()
    checks.append(_check("headerfooter", "Nothing hidden in header/footer", "pass" if not hf else "warn",
                         "Header and footer are empty" if not hf else "Header/footer text is often skipped by ATS parsers"))

    heads = [p.text.strip().upper() for p in doc.paragraphs if p.style.name == "Heading 1"]
    sections = expected_sections(resume)
    ok = heads == sections
    checks.append(_check("sections", "Standard headings, in order", "pass" if ok else "fail",
                         " → ".join(s.title() for s in sections) if ok else f"Expected {sections}, found {heads}"))

    text = "\n".join(p.text for p in doc.paragraphs)
    checks.append(_contact_check(resume, text))

    cov, missing = _coverage(resume, text, clean=False)
    checks.append(_check("content", "All your content is in the file", "pass" if cov >= 0.98 else "fail",
                         "Every word from the editor is present" if cov >= 0.98
                         else f"{round((1 - cov) * 100)}% of words are missing, e.g. {', '.join(missing[:5])}"))
    return {"ok": all(c["status"] != "fail" for c in checks), "pages": None, "checks": checks}
