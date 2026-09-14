"""Export tailored resume as HTML (printable to PDF)."""

from __future__ import annotations

from html import escape
from typing import Any


def tailored_resume_to_html(resume: dict[str, Any], title: str = "Resume") -> str:
    profile = resume.get("profile") or {}
    name = escape(str(profile.get("name") or "Candidate"))
    email = escape(str(profile.get("email") or ""))
    phone = escape(str(profile.get("phone") or ""))
    city = escape(str(profile.get("city") or ""))
    github = escape(str(profile.get("github") or ""))
    summary = escape(str(resume.get("summary") or ""))
    skills = resume.get("skills") or []
    experience = resume.get("experience") or []
    projects = resume.get("projects") or []
    education = resume.get("education") or []
    awards = resume.get("awards") or []

    def section_block(items: list, heading: str) -> str:
        if not items:
            return ""
        parts = [f"<h2>{escape(heading)}</h2>"]
        for it in items:
            if isinstance(it, dict):
                t = escape(str(it.get("title") or it.get("school") or ""))
                c = escape(str(it.get("content") or "")).replace("\n", "<br/>")
                extra = ""
                if it.get("major") or it.get("degree"):
                    extra = f"<div class='muted'>{escape(str(it.get('degree', '')))} {escape(str(it.get('major', '')))}</div>"
                parts.append(f"<div class='item'><h3>{t}</h3>{extra}<p>{c}</p></div>")
            else:
                parts.append(f"<p>{escape(str(it))}</p>")
        return "\n".join(parts)

    skills_html = ""
    if skills:
        skills_html = (
            "<h2>Skills</h2><p class='skills'>"
            + " · ".join(escape(str(s)) for s in skills)
            + "</p>"
        )

    contact = " · ".join(x for x in [email, phone, city, github] if x)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{escape(title)} — {name}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         max-width: 800px; margin: 40px auto; padding: 0 24px; color: #111; line-height: 1.45; }}
  h1 {{ font-size: 28px; margin: 0 0 4px; }}
  .contact {{ color: #555; font-size: 13px; margin-bottom: 20px; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid #ddd;
        padding-bottom: 4px; margin-top: 22px; color: #333; }}
  h3 {{ font-size: 14px; margin: 12px 0 4px; }}
  p {{ margin: 0 0 8px; font-size: 13px; }}
  .muted {{ color: #666; font-size: 12px; }}
  .skills {{ font-size: 13px; }}
  .item {{ margin-bottom: 10px; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>{name}</h1>
  <div class="contact">{contact}</div>
  {"<h2>Summary</h2><p>" + summary + "</p>" if summary else ""}
  {skills_html}
  {section_block(experience, "Experience")}
  {section_block(projects, "Projects")}
  {section_block(education, "Education")}
  {section_block(awards, "Awards")}
</body>
</html>
"""
