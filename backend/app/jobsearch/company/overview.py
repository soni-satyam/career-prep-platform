"""A very short, evidence-grounded company intro: what it does, when it was founded, where it is based.

Evidence is gathered from the company's own site (metadata, schema.org Organization markup, about text),
Wikipedia (only when the page really is this company) and web-search snippets. The LLM may use only that
evidence, and its answer is validated: a founding year that does not literally appear in the evidence is
discarded. When no LLM is available the same facts are extracted deterministically.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, Optional

from app.jobsearch.company.discover import PageInfo, extract_founded
from app.jobsearch.company.identify import name_tokens
from app.jobsearch.company.linkedin import LinkedInCompany

logger = logging.getLogger("careerprep.jobs")

LlmFn = Callable[[str, str], Awaitable[dict]]

SYSTEM = (
    "You write a very short company profile for a job seeker. Use ONLY the evidence provided; the official "
    "website is the most trustworthy part. Never guess or add facts from memory. If something is not stated "
    "in the evidence, use null. Reply with a single JSON object and nothing else."
)

_PROMPT = """Company: {name}

EVIDENCE:
{evidence}

Return JSON with exactly these keys:
{{"summary": "1-2 plain sentences, at most 45 words: what the company is and does, no marketing language",
  "what_it_does": "one short sentence, at most 20 words, on its main product or service",
  "founded": "4-digit year if the evidence states when the company was founded, else null",
  "headquarters": "city, country if stated, else null",
  "industry": "2-4 words, else null"}}"""


@dataclass
class Overview:
    summary: str = ""
    what_it_does: str = ""
    founded: Optional[str] = None
    headquarters: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None  # employee range, from the LinkedIn page snippet
    method: str = "none"        # llm | extracted | none


def wiki_relevant(name: str, text: str) -> bool:
    """Wikipedia's search is fuzzy; only trust a page that is about a company with this name."""
    t = (text or "")[:500].lower()
    toks = name_tokens(name)
    if not t or not toks or toks[0] not in t:
        return False
    return not any(w in t for w in ("may refer to", "fictional", "disambiguation", "is a surname", "is a given name"))


def trim_sentences(text: str, max_chars: int = 280) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= 80:
        return cut[: end + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def build_evidence(
    *, home_url: str, home: Optional[PageInfo], org: dict, about_text: str,
    wiki_text: str, wiki_url: str, snippets: list[dict], linkedin: Optional[LinkedInCompany] = None,
) -> tuple[str, list[str]]:
    """Returns (evidence text, source urls)."""
    parts: list[str] = []
    sources: list[str] = []
    site: list[str] = []
    if org.get("description"):
        site.append(f"Organization description: {org['description']}")
    if org.get("founded"):
        site.append(f"Organization founding date: {org['founded']}")
    if org.get("headquarters"):
        site.append(f"Organization address: {org['headquarters']}")
    if home:
        for k in ("description", "og:description", "twitter:description"):
            if home.meta.get(k):
                site.append(f"Site description: {home.meta[k]}")
                break
        if home.title:
            site.append(f"Site title: {home.title}")
        if home.text:
            site.append(f"Homepage text: {home.text[:1200]}")
    if about_text:
        site.append(f"About page text: {about_text[:1500]}")
    if site:
        parts.append("## Official website\n" + "\n".join(site))
        sources.append(home_url)
    if linkedin and linkedin.evidence():
        parts.append("## LinkedIn company page (from a search result)\n" + linkedin.evidence())
        sources.append(linkedin.url)
    if wiki_text:
        parts.append(f"## Wikipedia\n{wiki_text[:1500]}")
        if wiki_url:
            sources.append(wiki_url)
    snip = [f"- {r.get('title', '')}: {r.get('body', '')}" for r in (snippets or [])[:6] if r.get("body")]
    if snip:
        parts.append("## Web search snippets\n" + "\n".join(snip))
        sources += [r["href"] for r in (snippets or [])[:2] if r.get("href")]
    return "\n\n".join(parts)[:7000], list(dict.fromkeys(s for s in sources if s))


def _opt(v: Any, limit: int) -> str:
    if not isinstance(v, str):
        return ""
    v = " ".join(v.split())
    return "" if v.lower() in ("", "null", "none", "unknown", "n/a", "not stated", "not specified") else v[:limit]


def validate_llm(data: dict, evidence: str) -> Overview:
    """Keep only well-formed fields, and only a founding year the evidence actually contains."""
    founded = _opt(data.get("founded"), 8)
    year = re.match(r"^(\d{4})$", founded)
    if not (year and 1800 <= int(year.group(1)) <= date.today().year and year.group(1) in evidence):
        founded = ""
    return Overview(
        summary=trim_sentences(_opt(data.get("summary"), 600), 320),
        what_it_does=trim_sentences(_opt(data.get("what_it_does"), 300), 200),
        founded=founded or None,
        headquarters=_opt(data.get("headquarters"), 80) or None,
        industry=_opt(data.get("industry"), 50) or None,
        method="llm",
    )


def extract_overview(
    *, org: dict, home: Optional[PageInfo], wiki_text: str, snippets: list[dict], about_text: str,
    linkedin: Optional[LinkedInCompany] = None,
) -> Overview:
    """No-LLM fallback: first good description + regex-found founding year."""
    li = linkedin
    desc = (
        org.get("description")
        or (home.meta.get("og:description") or home.meta.get("description") if home else "")
        or (li.description if li else "")
        or wiki_text
        or next((r.get("body", "") for r in snippets or [] if r.get("body")), "")
        or about_text
    )
    haystacks = [org.get("founded") and f"Founded in {org['founded']}", li and li.founded and f"Founded in {li.founded}",
                 wiki_text, about_text,
                 " ".join(r.get("body", "") for r in snippets or [])]
    founded = None
    for h in haystacks:
        founded = extract_founded(h or "")
        if founded:
            break
    return Overview(
        summary=trim_sentences(desc, 280), founded=founded,
        headquarters=org.get("headquarters") or (li.headquarters if li else "") or None,
        industry=(li.industry if li else "") or None, size=(li.size if li else "") or None,
        method="extracted" if desc else "none",
    )


async def default_llm(system: str, user: str) -> dict:
    from app.agents.llm_utils import run_json_agent   # imported lazily: heavy, and optional in tests

    return await run_json_agent(system, user, temperature=0.1, cache_ttl=86400, est_output_tokens=350)


async def build_overview(
    name: str, *, home_url: str, home: Optional[PageInfo], org: dict, about_text: str,
    wiki_text: str, wiki_url: str, snippets: list[dict], llm: Optional[LlmFn] = None,
    linkedin: Optional[LinkedInCompany] = None,
) -> tuple[Overview, list[str]]:
    evidence, sources = build_evidence(
        home_url=home_url, home=home, org=org, about_text=about_text,
        wiki_text=wiki_text, wiki_url=wiki_url, snippets=snippets, linkedin=linkedin,
    )
    fallback = extract_overview(org=org, home=home, wiki_text=wiki_text, snippets=snippets, about_text=about_text,
                                linkedin=linkedin)
    if len(evidence) < 60:
        return fallback, sources
    try:
        data = await (llm or default_llm)(SYSTEM, _PROMPT.format(name=name, evidence=evidence))
        ov = validate_llm(data, evidence)
    except Exception as exc:  # noqa: BLE001 - the intro must never fail the whole lookup
        logger.info("company overview LLM unavailable: %s", type(exc).__name__)
        return fallback, sources
    if not ov.summary:
        return fallback, sources
    # facts the site itself states win over the model's reading of them
    ov.founded = org.get("founded") or ov.founded or (linkedin.founded if linkedin else None) or fallback.founded
    ov.headquarters = ov.headquarters or fallback.headquarters
    ov.industry = ov.industry or fallback.industry
    ov.size = fallback.size          # taken from LinkedIn as written, never from the model
    return ov, sources
