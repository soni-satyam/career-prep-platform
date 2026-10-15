from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Source priority (lower = shown first). Mirrors the product ordering:
# company career page -> Greenhouse -> Lever -> LinkedIn -> Naukri -> Indeed -> everything else.
SOURCE_PRIORITY: dict[str, int] = {
    "career_page": 0,
    "greenhouse": 1,
    "lever": 2,
    "ashby": 3,
    "linkedin": 4,
    "naukri": 5,
    "indeed": 6,
    "glassdoor": 7,
}
OTHER_PRIORITY = 8

SOURCE_LABELS: dict[str, str] = {
    "career_page": "Company career page",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "linkedin": "LinkedIn",
    "naukri": "Naukri",
    "indeed": "Indeed",
    "glassdoor": "Glassdoor",
    "adzuna": "Adzuna",
    "jooble": "Jooble",
    "remotive": "Remotive",
    "other": "Other portals",
}


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, OTHER_PRIORITY)


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source.replace("_", " ").title())


def classify_publisher(name: str | None) -> str:
    """Map a free-text publisher / site name ('LinkedIn', 'naukri.com') to a source key."""
    n = (name or "").lower()
    for key in ("linkedin", "naukri", "indeed", "glassdoor"):
        if key in n:
            return key
    return "other"


@dataclass
class JobPosting:
    title: str
    company: str
    url: str
    source: str                       # key of SOURCE_LABELS
    location: str = ""
    remote: bool = False
    work_mode: str = ""               # remote | hybrid | onsite | "" (unknown)
    posted_at: Optional[datetime] = None
    description: str = ""             # plain text
    employment_type: str = ""
    seniority: str = ""
    salary_min: Optional[float] = None   # annual, in salary_currency
    salary_max: Optional[float] = None
    salary_currency: str = ""
    salary_text: str = ""
    experience_min: Optional[float] = None
    experience_max: Optional[float] = None
    external_id: str = ""
    also_on: list[dict] = field(default_factory=list)

    @property
    def priority(self) -> int:
        return source_priority(self.source)

    @property
    def dedupe_key(self) -> str:
        from app.jobsearch.text import normalize_company, normalize_title

        loc = (self.location or "").lower().split(",")[0].strip()
        return f"{normalize_company(self.company)}|{normalize_title(self.title)}|{loc}"

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{self.external_id or self.url}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class SearchFilters:
    q: str = ""
    location: str = ""
    country: str = ""                 # ISO-2, used by aggregators (default from settings)
    work_mode: str = ""               # "", remote, hybrid, onsite
    salary_min: Optional[float] = None
    salary_currency: str = ""
    include_unspecified_salary: bool = True
    experience_min: Optional[float] = None
    experience_max: Optional[float] = None
    employment_type: str = ""         # full-time, part-time, contract, internship
    posted_within_days: Optional[int] = None
    company: str = ""
    sources: list[str] = field(default_factory=list)   # empty = all
    sort: str = "priority"            # priority | recent | match
