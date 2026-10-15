"""Pure helpers: read a web page and pull out what company search needs. No network access.

Uses only the standard library (`html.parser`, `json`, `re`), so it is fast to test and has no extra
dependencies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterator, Optional
from urllib.parse import unquote, urldefrag, urljoin, urlparse

from app.jobsearch.company.identify import registrable_domain

# ------------------------------------------------------------------ page model


@dataclass
class Anchor:
    href: str
    text: str
    lines: list[str]


@dataclass
class PageInfo:
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    anchors: list[Anchor] = field(default_factory=list)
    srcs: list[str] = field(default_factory=list)          # iframe / script / embed sources
    jsonld: list[str] = field(default_factory=list)        # raw <script type="application/ld+json">
    json_scripts: list[str] = field(default_factory=list)  # raw <script type="application/json"> (e.g. __NEXT_DATA__)
    text: str = ""                                         # visible text, whitespace-collapsed, capped
    next_href: str = ""


_LINE_BREAK_TAGS = {"div", "p", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "td", "tr", "section", "article", "span"}


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.anchors: list[Anchor] = []
        self.srcs: list[str] = []
        self.jsonld: list[str] = []
        self.json_scripts: list[str] = []
        self.next_href = ""
        self._text: list[str] = []
        self._in_title = False
        self._skip = 0
        self._script_type: Optional[str] = None
        self._script_id = ""
        self._script_buf: list[str] = []
        self._a: Optional[dict] = None

    # -- anchors
    def _close_anchor(self) -> None:
        a, self._a = self._a, None
        if not a or not a["href"]:
            return
        lines = [" ".join(l.split()) for l in "".join(a["parts"]).split("\n")]
        lines = [l for l in lines if l]
        self.anchors.append(Anchor(href=a["href"], text=" ".join(lines), lines=lines))

    def handle_starttag(self, tag: str, attrs: list) -> None:
        at = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (at.get("property") or at.get("name") or "").lower()
            if key and at.get("content"):
                self.meta.setdefault(key, at["content"].strip())
        elif tag == "a":
            if self._a is not None:
                self._close_anchor()
            self._a = {"href": at.get("href", "").strip(), "parts": []}
        elif tag == "link" and "next" in at.get("rel", "").lower().split():
            self.next_href = at.get("href", "")
        if tag in ("iframe", "script", "embed") and at.get("src"):
            self.srcs.append(at["src"])
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            if tag == "script":
                self._script_type = at.get("type", "").lower()
                self._script_id = at.get("id", "")
                self._script_buf = []
        if tag in _LINE_BREAK_TAGS:
            if self._a is not None:
                self._a["parts"].append("\n")
            self._text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._a is not None:
            self._close_anchor()
        elif tag in ("script", "style", "noscript"):
            if tag == "script" and self._script_type is not None:
                raw = "".join(self._script_buf).strip()
                if raw:
                    if "ld+json" in self._script_type:
                        self.jsonld.append(raw)
                    elif "json" in self._script_type or self._script_id in ("__NEXT_DATA__", "__NUXT_DATA__"):
                        self.json_scripts.append(raw)
                self._script_type = None
            self._skip = max(0, self._skip - 1)
        if tag in _LINE_BREAK_TAGS and self._a is not None:
            self._a["parts"].append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip:
            if self._script_type is not None:
                self._script_buf.append(data)
            return
        if self._a is not None:
            self._a["parts"].append(data)
        self._text.append(data)

    def close(self) -> None:  # noqa: D401
        super().close()
        if self._a is not None:
            self._close_anchor()


def parse_page(html: str) -> PageInfo:
    c = _Collector()
    try:
        c.feed(html or "")
        c.close()
    except Exception:  # noqa: BLE001 - malformed markup must never break a lookup
        pass
    return PageInfo(
        title=" ".join(c.title.split()), meta=c.meta, anchors=c.anchors, srcs=c.srcs,
        jsonld=c.jsonld, json_scripts=c.json_scripts,
        text=" ".join("".join(c._text).split())[:8000], next_href=c.next_href,
    )


def absolute(href: str, base: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return ""
    url = urldefrag(urljoin(base, href))[0]
    return url if url.startswith(("http://", "https://")) else ""


# ------------------------------------------------------------------ ATS detection


@dataclass(frozen=True)
class AtsBoard:
    provider: str     # greenhouse | lever | ashby | workable | smartrecruiters | recruitee
    slug: str


_ATS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greenhouse", re.compile(
        r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=|embed/)?([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"(?:jobs(?:\.eu)?\.lever\.co|api\.lever\.co/v0/postings)/([A-Za-z0-9_.-]+)", re.I)),
    ("ashby", re.compile(
        r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/([A-Za-z0-9_.%-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/(?:api/v\d/(?:widget/)?accounts/)?([a-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"//([a-z0-9-]+)\.workable\.com", re.I)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("recruitee", re.compile(r"//([a-z0-9-]+)\.recruitee\.com", re.I)),
]
_BAD_SLUGS = {
    "embed", "job_app", "job_board", "jobs", "api", "www", "apply", "app", "static", "assets", "careers",
    "resources", "help", "support", "widget", "v1", "v2", "undefined", "null",
}


def detect_boards(*texts: str) -> list[AtsBoard]:
    """Find Greenhouse / Lever / Ashby / Workable / SmartRecruiters / Recruitee boards mentioned in text or URLs."""
    found: list[AtsBoard] = []
    for text in texts:
        for provider, pat in _ATS_PATTERNS:
            for m in pat.finditer(text or ""):
                slug = next((g for g in m.groups() if g), "")
                slug = unquote(slug).strip("/.")
                if not slug or slug.lower() in _BAD_SLUGS:
                    continue
                if provider in ("greenhouse", "workable", "recruitee"):
                    slug = slug.lower()
                b = AtsBoard(provider, slug)
                if b not in found:
                    found.append(b)
    return found


def board_from_url(url: str) -> Optional[AtsBoard]:
    b = detect_boards(url)
    return b[0] if b else None


# ------------------------------------------------------------------ career page discovery

_CAREER_TEXT = re.compile(
    r"\b(careers?|jobs?|join (us|our team|the team)|we(?:'|’)?re hiring|we are hiring|work (with|at|for) us|"
    r"open (roles|positions)|openings|opportunities|hiring)\b", re.I)
_CAREER_PATH = re.compile(
    r"/(careers?|jobs?|join(-us|-our-team|-the-team)?|work-with-us|work-at-[\w-]+|openings|open-positions|"
    r"opportunities|hiring|we-are-hiring)(/|$)", re.I)
_NOT_CAREER_PATH = re.compile(r"/(blog|press|news|investors?|login|sign-?in|privacy|terms|cookies?|help|docs|legal)(/|$)", re.I)

COMMON_CAREER_PATHS = [
    "/careers", "/jobs", "/careers/", "/join-us", "/company/careers", "/about/careers",
    "/work-with-us", "/careers/jobs", "/open-positions", "/join",
]


@dataclass
class CareerLink:
    url: str
    text: str
    score: int
    board: Optional[AtsBoard] = None


def find_career_links(page: PageInfo, base_url: str) -> list[CareerLink]:
    """Rank the links on a page by how likely they lead to the company's job listings."""
    best: dict[str, CareerLink] = {}
    for a in page.anchors:
        url = absolute(a.href, base_url)
        if not url:
            continue
        u = urlparse(url)
        board = board_from_url(url)
        same = registrable_domain((u.hostname or "").removeprefix("www.")) == registrable_domain(
            (urlparse(base_url).hostname or "").removeprefix("www."))
        if not same and not board:
            continue
        score = 0
        if _CAREER_TEXT.search(a.text) and len(a.text) <= 60:
            score += 3
        if _CAREER_PATH.search(u.path + "/"):
            score += 2
        if (u.hostname or "").startswith(("careers.", "jobs.")):
            score += 3
        if board:
            score += 5
        if score and _NOT_CAREER_PATH.search(u.path) and not board:
            score -= 3
        if score < 3:
            continue
        cur = best.get(url)
        if cur is None or score > cur.score:
            best[url] = CareerLink(url=url, text=a.text[:60], score=score, board=board)
    return sorted(best.values(), key=lambda c: (-c.score, len(c.url)))


def looks_like_careers_page(page: PageInfo) -> bool:
    """A page we reached by guessing a path: does it plausibly list jobs?"""
    blob = f"{page.title} {page.meta.get('og:title', '')} {page.meta.get('description', '')}".lower()
    if re.search(r"\b(careers?|jobs?|open (roles|positions)|join (us|our team)|hiring)\b", blob):
        return True
    return bool(page.jsonld and any("JobPosting" in j for j in page.jsonld)) or bool(detect_boards(*page.srcs))


# ------------------------------------------------------------------ job links on a listing page

_JOB_WORDS = {
    "job", "jobs", "career", "careers", "position", "positions", "opening", "openings", "opportunity",
    "opportunities", "vacancy", "vacancies", "role", "roles", "apply", "join", "o", "j", "postings",
}
_GENERIC_ANCHOR = {
    "apply", "apply now", "learn more", "read more", "view all jobs", "see all jobs", "all jobs", "careers",
    "jobs", "view job", "view details", "details", "view role", "see role", "open positions", "view",
    "view all", "see all", "see more", "show more", "back", "next", "previous", "home", "join us",
}


@dataclass
class ListedJob:
    title: str
    url: str
    extras: list[str] = field(default_factory=list)   # other text lines inside the link (team, location ...)


def extract_job_links(page: PageInfo, base_url: str, *, min_group: int = 3) -> list[ListedJob]:
    """Links that look like individual job postings.

    A job listing is many links sharing one URL template (…/careers/<slug>), so links are grouped by the
    path up to the job-ish segment and only groups of `min_group`+ are kept. That drops nav links such as
    "Careers" or "Apply" that appear once. Links on ATS hosts are always kept.
    """
    base = absolute(base_url, base_url)
    groups: dict[tuple[str, str], list[ListedJob]] = {}
    for a in page.anchors:
        url = absolute(a.href, base_url)
        if not url or url == base:
            continue
        u = urlparse(url)
        segs = [s for s in u.path.split("/") if s]
        idx = next((i for i, s in enumerate(segs) if s.lower() in _JOB_WORDS), None)
        board = board_from_url(url)
        if idx is None or idx >= len(segs) - 1:
            if not (board and len(segs) >= 2):
                continue
            idx = max(0, len(segs) - 2)
        lines = [l for l in a.lines if l.lower() not in _GENERIC_ANCHOR]
        if not lines or not (3 <= len(lines[0]) <= 140):
            continue
        key = ((u.hostname or ""), "/".join(segs[: idx + 1]).lower())
        groups.setdefault(key, []).append(ListedJob(title=lines[0], url=url, extras=lines[1:4]))
    out: list[ListedJob] = []
    seen: set[str] = set()
    for (host, _), items in groups.items():
        if len(items) < min_group and not any(board_from_url(i.url) for i in items):
            continue
        for it in items:
            if it.url not in seen:
                seen.add(it.url)
                out.append(it)
    return out


def next_page_url(page: PageInfo, base_url: str) -> str:
    if page.next_href:
        return absolute(page.next_href, base_url)
    for a in page.anchors:
        if a.text.strip().lower() in ("next", "next page", "next ›", "next »", "›", "»", "load more"):
            return absolute(a.href, base_url)
    return ""


# ------------------------------------------------------------------ jobs inside embedded JSON

_TITLE_KEYS = ("title", "jobTitle", "job_title", "positionTitle", "name", "text", "role")
_URL_KEYS = ("absolute_url", "hostedUrl", "applyUrl", "jobUrl", "job_url", "careers_url", "applicationUrl", "url", "link", "href")
_META_KEYS = {
    "location", "locations", "city", "office", "department", "departments", "team", "employmenttype",
    "employment_type", "workplacetype", "commitment", "remote", "country", "jobtype", "type",
}


def _first_str(d: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _loc_text(d: dict) -> str:
    for k in ("location", "locations", "city", "office", "offices"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            s = _first_str(v, ("name", "label", "city", "text"))
            if s:
                return s
        if isinstance(v, list):
            parts = []
            for x in v:
                if isinstance(x, str):
                    parts.append(x)
                elif isinstance(x, dict):
                    parts.append(_first_str(x, ("name", "label", "city", "text")))
            parts = [p for p in parts if p]
            if parts:
                return " | ".join(parts[:4])
    return ""


def _looks_like_job(d: Any) -> bool:
    if not isinstance(d, dict):
        return False
    title = _first_str(d, _TITLE_KEYS)
    if not (3 <= len(title) <= 140) or not _first_str(d, _URL_KEYS):
        return False
    return any(k.lower() in _META_KEYS for k in d)


def _walk_lists(node: Any, depth: int = 0) -> Iterator[list]:
    if depth > 12:
        return
    if isinstance(node, list):
        yield node
        for n in node[:300]:
            yield from _walk_lists(n, depth + 1)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_lists(v, depth + 1)


def extract_embedded_jobs(page: PageInfo, base_url: str) -> list[dict]:
    """Jobs found in JSON the page embeds (Next.js `__NEXT_DATA__`, hydration blobs ...).

    Returns plain dicts {title, url, location, department, employment_type, posted}.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for raw in page.json_scripts:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for lst in _walk_lists(data):
            items = [x for x in lst if isinstance(x, dict)]
            if len(items) < 2:
                continue
            jobs = [x for x in items if _looks_like_job(x)]
            if len(jobs) < 2 or len(jobs) < 0.6 * len(items):
                continue
            for x in jobs:
                url = absolute(_first_str(x, _URL_KEYS), base_url)
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append({
                    "title": _first_str(x, _TITLE_KEYS),
                    "url": url,
                    "location": _loc_text(x),
                    "department": _first_str(x, ("department", "team")),
                    "employment_type": _first_str(x, ("employmentType", "employment_type", "commitment", "jobType")),
                    "posted": _first_str(x, ("datePosted", "postedAt", "published_at", "publishedAt", "createdAt", "created_at")),
                })
    return out


# ------------------------------------------------------------------ organization facts

_FOUNDED_RES = [
    re.compile(r"\b(?:founded|established|incorporated)\b[:\s]+(?:in|on|back in)?\s*(?:[A-Za-z]+\.?\s+(?:\d{1,2},?\s*)?)?((?:18|19|20)\d{2})\b", re.I),
    re.compile(r"\bfounded\s+by\b[^.]{0,80}?\bin\s+((?:18|19|20)\d{2})\b", re.I),
    re.compile(r"\best\.?\s*((?:18|19|20)\d{2})\b", re.I),
]


def extract_founded(text: str) -> Optional[str]:
    from datetime import date

    for pat in _FOUNDED_RES:
        m = pat.search(text or "")
        if m and 1800 <= int(m.group(1)) <= date.today().year:
            return m.group(1)
    return None


_ORG_TYPES = {"Organization", "Corporation", "LocalBusiness", "NGO", "OnlineBusiness", "EducationalOrganization"}


def _walk_dicts(node: Any) -> Iterator[dict]:
    if isinstance(node, list):
        for n in node:
            yield from _walk_dicts(n)
    elif isinstance(node, dict):
        yield node
        for k in ("@graph", "mainEntity", "publisher", "provider"):
            if k in node:
                yield from _walk_dicts(node[k])


def parse_organization(jsonld_blocks: list[str]) -> dict:
    """Facts from schema.org Organization markup: name, description, founded (year), headquarters, logo."""
    for raw in jsonld_blocks:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for n in _walk_dicts(data):
            t = n.get("@type")
            types = t if isinstance(t, list) else [t]
            if not (set(types) & _ORG_TYPES):
                continue
            founded = None
            fd = str(n.get("foundingDate") or "")
            m = re.match(r"(\d{4})", fd)
            if m:
                founded = m.group(1)
            addr = n.get("address") or n.get("location") or {}
            hq = ""
            if isinstance(addr, str):
                hq = addr
            elif isinstance(addr, dict):
                a = addr.get("address") if isinstance(addr.get("address"), dict) else addr
                bits = [a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry") if isinstance(a.get("addressCountry"), str) else None]
                hq = ", ".join(b for b in bits if isinstance(b, str) and b)
            logo = n.get("logo")
            if isinstance(logo, dict):
                logo = logo.get("url")
            return {
                "name": n.get("name") if isinstance(n.get("name"), str) else "",
                "description": n.get("description") if isinstance(n.get("description"), str) else "",
                "founded": founded, "headquarters": hq,
                "logo": logo if isinstance(logo, str) else "",
            }
    return {}
