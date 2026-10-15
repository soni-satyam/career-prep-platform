"""What a company's LinkedIn page tells us, read from web-search results only.

linkedin.com itself is never fetched: it sits behind a login wall, blocks automated access and its terms
forbid scraping. A search engine's result for `linkedin.com/company/<slug>` already carries the page's
title and a snippet that usually holds the tagline, the follower count and often the About facts
(website, industry, company size, headquarters, founded). That is enough to identify a young company
that has no Wikipedia page and a thin website, and the company slug is a strong hint for its job-board slug.

Snippet formats vary, so every field is optional and parsing never raises.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.jobsearch.company.identify import (
    company_matches, core, domain_name_score, domain_of, is_blocked, looks_like_url, to_url,
)

_COMPANY_URL = re.compile(r"^https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/([A-Za-z0-9_%.\-]+)", re.I)
_LABELS = ("Website", "Industry", "Company size", "Headquarters", "Type", "Founded", "Specialties", "Locations", "Phone")
_LABEL_RE = re.compile(r"(?:^|[.\s|·•])(" + "|".join(_LABELS) + r")\s*[:.]\s*", re.I)
_FOLLOWERS_RE = re.compile(r"([\d][\d,.]*\s*[KkMm]?)\+?\s+followers", re.I)
_SIZE_RE = re.compile(r"(\d[\d,]*(?:\s*[-–]\s*\d[\d,]*|\+)?)\s+employees", re.I)
_NOT_SLUGS = {"unavailable", "jobs", "linkedin", "company"}


@dataclass
class LinkedInCompany:
    slug: str
    url: str
    name: str
    description: str = ""
    followers: str = ""
    size: str = ""
    headquarters: str = ""
    industry: str = ""
    founded: str = ""
    website: str = ""

    @property
    def jobs_url(self) -> str:
        return f"https://www.linkedin.com/company/{self.slug}/jobs/"

    def evidence(self) -> str:
        bits = []
        if self.description:
            bits.append(f"Description: {self.description}")
        for label, v in (("Industry", self.industry), ("Company size", self.size), ("Headquarters", self.headquarters),
                         ("Founded", self.founded), ("Website", self.website), ("Followers", self.followers)):
            if v:
                bits.append(f"{label}: {v}")
        return "\n".join(bits)


def _clean_name(title: str) -> str:
    t = " ".join((title or "").split())
    t = re.sub(r"\s*[|\-–—:]\s*LinkedIn\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s*[|\-–—:]\s*Overview\b.*$", "", t, flags=re.I)
    return t.split(" | ")[0].strip()


def parse_snippet(body: str) -> dict:
    """Pull tagline / About facts out of a LinkedIn company-page snippet."""
    text = " ".join((body or "").split())
    out: dict[str, str] = {}
    m = _FOLLOWERS_RE.search(text)
    if m:
        out["followers"] = m.group(1).strip()
    matches = list(_LABEL_RE.finditer(text))
    for i, lm in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[lm.end():end].strip(" .|·•,")
        if value:
            out.setdefault(lm.group(1).lower(), value[:160])
    if "company size" not in out:
        sm = _SIZE_RE.search(text)
        if sm:
            out["company size"] = f"{sm.group(1).strip()} employees"
    # tagline / description: what follows "N followers on LinkedIn." or what precedes the first label
    head = text[: matches[0].start()] if matches else text
    fm = re.search(r"followers on LinkedIn\.?\s*", head, re.I)
    desc = head[fm.end():] if fm else head
    desc = re.sub(r"^(?:About us|Overview)\s*[:.]?\s*", "", desc.strip(), flags=re.I).strip(" |·•")
    if desc and not re.fullmatch(r"[\d,.\sKkMm+]*followers.*", desc, re.I):
        out["description"] = desc[:600]
    return out


def parse_result(r: dict) -> Optional[LinkedInCompany]:
    url = r.get("href") or r.get("url") or ""
    m = _COMPANY_URL.match(url)
    if not m:
        return None
    slug = m.group(1).strip("/.").lower()
    if not slug or slug in _NOT_SLUGS or "/" in slug:
        return None
    f = parse_snippet(r.get("body", ""))
    website = f.get("website", "").split()[0].strip(".,") if f.get("website") else ""
    if website and looks_like_url(website) and not is_blocked(domain_of(to_url(website))):
        website = to_url(website)
    else:
        website = ""
    founded = re.search(r"\b((?:18|19|20)\d{2})\b", f.get("founded", ""))
    return LinkedInCompany(
        slug=slug, url=f"https://www.linkedin.com/company/{slug}/", name=_clean_name(r.get("title", "")) or slug.replace("-", " ").title(),
        description=f.get("description", ""), followers=f.get("followers", ""), size=f.get("company size", ""),
        headquarters=f.get("headquarters", ""), industry=f.get("industry", ""), founded=founded.group(1) if founded else "",
        website=website,
    )


def pick_linkedin(results: list[dict], name: str, domain: str = "") -> list[LinkedInCompany]:
    """Company pages that are really this company, best first."""
    merged: dict[str, tuple[int, LinkedInCompany]] = {}
    for rank, r in enumerate(results or []):
        li = parse_result(r)
        if not li:
            continue
        if li.slug in merged:                       # same page twice: keep the first, fill its gaps from the second
            first = merged[li.slug][1]
            for f in ("description", "followers", "size", "headquarters", "industry", "founded", "website"):
                if not getattr(first, f) and getattr(li, f):
                    setattr(first, f, getattr(li, f))
        else:
            merged[li.slug] = (rank, li)
    scored: list[tuple[float, LinkedInCompany]] = []
    for rank, li in merged.values():
        score = 0.0
        if company_matches(li.name, name):
            score += 3
        if core(li.slug.replace("-", "")) == core(name):
            score += 3
        elif len(core(name)) >= 4 and core(name) in li.slug.replace("-", ""):
            score += 1
        if domain and li.website and domain_of(li.website) == domain:
            score += 4
        elif domain and domain_name_score(domain, li.name) >= 2:
            score += 1
        if score < 3:
            continue
        scored.append((score + max(0, 3 - rank) * 0.1, li))
    scored.sort(key=lambda x: -x[0])
    return [li for _, li in scored]
