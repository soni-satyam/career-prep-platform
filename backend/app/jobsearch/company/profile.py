from __future__ import annotations

from dataclasses import dataclass, field

from typing import Optional

from app.jobsearch.company.discover import AtsBoard
from app.jobsearch.company.linkedin import LinkedInCompany
from app.jobsearch.company.overview import Overview


@dataclass
class CompanyProfile:
    key: str
    name: str
    website: str = ""
    domain: str = ""
    logo: str = ""
    overview: Overview = field(default_factory=Overview)
    career_url: str = ""
    career_status: str = "not_found"          # found | guessed | not_found
    boards: list[AtsBoard] = field(default_factory=list)    # ATS boards seen on the company's own pages
    hint_boards: list[AtsBoard] = field(default_factory=list)   # boards named in search results: verified before use
    linkedin: Optional[LinkedInCompany] = None
    sources: list[str] = field(default_factory=list)        # pages the intro was built from
    alternatives: list[dict] = field(default_factory=list)  # other companies the query could mean
    links: list[dict] = field(default_factory=list)         # search pages on other portals
    aliases: list[str] = field(default_factory=list)        # other legal / brand names, for matching job ads
    confidence: str = "low"                                 # high | medium | low: did we find the right company?
    notes: list[str] = field(default_factory=list)
