"""Turn what the user typed ("Stripe", "acme robotics", "acme.io") into a company identity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus, urlparse

_LEGAL = {
    "inc", "incorporated", "llc", "ltd", "limited", "pvt", "private", "plc", "corp", "corporation",
    "co", "company", "gmbh", "ag", "sa", "pte", "llp", "opc", "the",
}

# Sites that describe companies but are never the company's own site.
BLOCKED_DOMAINS = {
    "wikipedia.org", "wikidata.org", "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "tiktok.com", "crunchbase.com", "glassdoor.com", "glassdoor.co.in", "indeed.com",
    "naukri.com", "ambitionbox.com", "zaubacorp.com", "tracxn.com", "pitchbook.com", "bloomberg.com",
    "reuters.com", "forbes.com", "techcrunch.com", "wellfound.com", "angel.co", "g2.com", "trustpilot.com",
    "quora.com", "reddit.com", "medium.com", "github.com", "play.google.com", "apps.apple.com", "owler.com",
    "zoominfo.com", "craft.co", "cbinsights.com", "dnb.com", "comparably.com", "tofler.in",
    "thecompanycheck.com", "yourstory.com", "inc42.com", "entrackr.com", "economictimes.indiatimes.com",
    "business-standard.com", "moneycontrol.com", "britannica.com", "instahyre.com", "monster.com",
    "ziprecruiter.com", "simplyhired.com", "shine.com", "foundit.in", "apollo.io", "rocketreach.co",
    "sec.gov", "opencorporates.com", "stackoverflow.com", "ycombinator.com", "producthunt.com",
}

_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu"}


def clean_name(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip())


def name_tokens(name: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", name.lower())
    kept = [t for t in toks if t not in _LEGAL]
    return kept or toks


def core(name: str) -> str:
    return "".join(name_tokens(name))


def looks_like_url(q: str) -> bool:
    q = (q or "").strip()
    return bool(q) and " " not in q and bool(re.match(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?(/\S*)?$", q, re.I))


def to_url(q: str) -> str:
    q = q.strip()
    return q if re.match(r"^https?://", q, re.I) else f"https://{q}"


def normalize_url(url: str) -> str:
    """Stable form for a site address: scheme://host/path with at least a "/" path."""
    p = urlparse(url or "")
    if not p.scheme or not p.netloc:
        return url or ""
    return f"{p.scheme}://{p.netloc}{p.path or '/'}"


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def registrable_label(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else domain


def registrable_domain(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def same_site(a: str, b: str) -> bool:
    return registrable_domain(domain_of(a) or a) == registrable_domain(domain_of(b) or b)


def is_blocked(domain: str) -> bool:
    d = registrable_domain(domain)
    return d in BLOCKED_DOMAINS or domain in BLOCKED_DOMAINS


def domain_name_score(domain: str, name: str) -> int:
    """How strongly a domain looks like it belongs to `name` (0 = unrelated, 3 = exact)."""
    label = registrable_label(domain).replace("-", "")
    toks = name_tokens(name)
    c = "".join(toks)
    if not label or not c:
        return 0
    if label == c:
        return 3
    if len(label) >= 4 and len(c) >= 4 and (label in c or c in label):
        return 2
    if len(toks) >= 3 and label == "".join(t[0] for t in toks):    # tata consultancy services -> tcs
        return 2
    if toks and len(toks[0]) >= 4 and label == toks[0]:
        return 2
    return 0


@dataclass
class Site:
    url: str
    domain: str
    title: str
    score: float


def pick_sites(results: list[dict], name: str, limit: int = 3) -> list[Site]:
    """Rank web-search results as candidates for the company's own website."""
    toks = name_tokens(name)
    seen: set[str] = set()
    sites: list[Site] = []
    for rank, r in enumerate(results or []):
        url = r.get("href") or r.get("url") or ""
        dom = domain_of(url)
        if not dom or is_blocked(dom):
            continue
        root = registrable_domain(dom)
        if root in seen:
            continue
        seen.add(root)
        blob = f"{r.get('title', '')} {r.get('body', '')}".lower()
        score = domain_name_score(dom, name) * 2
        if toks and all(t in blob for t in toks):
            score += 1
        if score <= 0:
            continue
        score += max(0, 3 - rank) * 0.1
        p = urlparse(url)
        sites.append(Site(url=f"{p.scheme}://{p.netloc}/", domain=dom, title=r.get("title", ""), score=score))
    sites.sort(key=lambda s: -s.score)
    return sites[:limit]


def guess_domains(name: str) -> list[str]:
    c = core(name)
    if len(c) < 3:
        return []
    return [f"{c}{tld}" for tld in (".com", ".io", ".ai", ".co", ".in", ".app")]


_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")


def slug_candidates(name: str, domain: str = "", extra: tuple[str, ...] | list[str] = ()) -> list[str]:
    """Likely ATS board slugs: acmerobotics, acme-robotics, the website's own label, and any known slug
    (a company's LinkedIn slug is very often its job-board slug too)."""
    toks = name_tokens(name)
    out: list[str] = []
    for s in ("".join(toks), "-".join(toks), registrable_label(domain).replace("_", "-") if domain else "", *extra):
        if s and _SLUG_OK.match(s) and s not in out:
            out.append(s)
    return out


def company_key(name: str) -> str:
    return "-".join(name_tokens(name))[:60] or "company"


_GENERIC = {
    "technologies", "technology", "tech", "labs", "lab", "software", "systems", "india", "global", "group",
    "holdings", "solutions", "services", "platforms", "international", "digital", "ai", "io", "app",
}


def company_matches(job_company: str, name: str, aliases: tuple[str, ...] | list[str] = ()) -> bool:
    """Token-level match used to keep only this company's jobs from aggregator results.

    "Stripe, Inc." and "Meta Platforms" match "Stripe" / "Meta"; "Metabase" and "Stripe Capital" do not.
    """
    a = name_tokens(job_company or "")
    if not a:
        return False
    for candidate in (name, *aliases):
        b = name_tokens(candidate or "")
        if not b:
            continue
        if a == b or "".join(a) == "".join(b):
            return True
        if a[: len(b)] == b and all(t in _GENERIC for t in a[len(b):]):
            return True
        if b[: len(a)] == a and all(t in _GENERIC for t in b[len(a):]):
            return True
    return False


def browse_links(name: str, key: str, linkedin_slug: str = "") -> list[dict]:
    """Search pages on other portals. Plain links, nothing is scraped from them."""
    q = quote_plus(name)
    linkedin = (f"https://www.linkedin.com/company/{quote(linkedin_slug)}/jobs/" if linkedin_slug
                else f"https://www.linkedin.com/jobs/search/?keywords={q}")
    return [
        {"label": "LinkedIn", "url": linkedin},
        {"label": "Naukri", "url": f"https://www.naukri.com/{quote(key)}-jobs"},
        {"label": "Indeed", "url": f"https://www.indeed.com/jobs?q={q}"},
        {"label": "Wellfound", "url": f"https://wellfound.com/company/{quote(key)}/jobs"},
        {"label": "Google Jobs", "url": f"https://www.google.com/search?q={q}+jobs&ibp=htl;jobs"},
    ]
