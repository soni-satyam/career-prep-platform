"""Text helpers: HTML -> text, skills / experience / seniority extraction, normalisation."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Iterable, Optional

# ----------------------------------------------------------------------- html

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6])\s*/?>", re.I)
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def html_to_text(raw: str | None, limit: int = 20000) -> str:
    if not raw:
        return ""
    s = raw
    # Greenhouse double-escapes its HTML ("&lt;p&gt;"); unescape until stable (max 2x).
    for _ in range(2):
        if "&lt;" in s or "&gt;" in s:
            s = html.unescape(s)
    s = _BR_RE.sub("\n", s)
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = _WS_RE.sub(" ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()[:limit]


def snippet(text: str, n: int = 280) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# -------------------------------------------------------------- normalisation

_COMPANY_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|limited|pvt|private|corp|corporation|gmbh|co|company|technologies|technology|india)\b\.?",
    re.I,
)


def normalize_company(name: str | None) -> str:
    n = _COMPANY_SUFFIX.sub("", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", "", n)


def normalize_title(title: str | None) -> str:
    t = (title or "").lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)           # drop "(Remote)" / "[Bengaluru]"
    t = re.sub(r"\b(sr|snr)\b\.?", "senior", t)
    t = re.sub(r"\b(jr)\b\.?", "junior", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


_LOCATION_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "gurgaon": "gurugram",
    "gurugram": "gurugram",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "new delhi": "delhi",
    "ncr": "delhi",
    "delhi ncr": "delhi",
    "poona": "pune",
    "hyderabad": "hyderabad",
}


def location_tokens(text: str | None) -> set[str]:
    t = (text or "").lower()
    out: set[str] = set()
    for alias, canon in _LOCATION_ALIASES.items():
        if alias in t:
            out.add(canon)
    for tok in re.split(r"[^a-z0-9]+", t):
        if len(tok) >= 3 and tok not in {"and", "the", "area", "region", "city", "india"}:
            out.add(_LOCATION_ALIASES.get(tok, tok))
    return out


def location_matches(job_location: str | None, wanted: str | None) -> bool:
    if not (wanted or "").strip():
        return True
    want = location_tokens(wanted)
    if not want:
        return True
    return bool(want & location_tokens(job_location))


# --------------------------------------------------------------- query tokens

_STOP = {"a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "jobs", "job", "role", "roles"}
_EQUIV = {
    "developer": "engineer", "programmer": "engineer", "engineering": "engineer", "swe": "engineer",
    "sde": "engineer", "sdet": "engineer", "dev": "engineer", "devs": "engineer",
    "frontend": "frontend", "front": "frontend", "backend": "backend", "back": "backend",
    "fullstack": "fullstack", "full": "fullstack",
    "ml": "ml", "ai": "ai", "sr": "senior", "jr": "junior", "mgr": "manager",
}


def title_tokens(text: str | None) -> list[str]:
    toks = re.split(r"[^a-z0-9+#]+", (text or "").lower())
    out = []
    for t in toks:
        if not t or t in _STOP:
            continue
        out.append(_EQUIV.get(t, t))
    return out


def query_matches_job(query: str, title: str, description: str) -> bool:
    """Loose relevance test for sources that cannot search server-side (ATS boards).

    - every query word in the title                       -> match
    - otherwise a multi-word query needs at least one word in the title, and every word
      not in the title must be mentioned 2+ times in the description (a real requirement,
      not a passing mention).
    """
    qt = title_tokens(query)
    if not qt:
        return True
    tt = set(title_tokens(title))
    missing = [t for t in qt if t not in tt]
    if not missing:
        return True
    if len(qt) >= 2 and len(missing) == len(qt):
        return False
    desc = (description or "").lower()[:4000]
    return all(desc.count(t) >= 2 for t in missing)


# --------------------------------------------------------------------- skills

# canonical|alias|alias ...   (matching is case-insensitive, whole-token)
_SKILL_DEFS = """
Python|python3
Java
JavaScript|js|ecmascript
TypeScript|ts
Go|golang|go lang
Rust
C++|cpp
C#|csharp|c sharp
.NET|dotnet|asp.net
Kotlin
Swift
Objective-C
Ruby|ruby on rails|rails
PHP|laravel|symfony
Scala
R Programming|r language
MATLAB
Bash|shell scripting|shell
SQL|t-sql|pl/sql
NoSQL
PostgreSQL|postgres
MySQL
MongoDB|mongo
Redis
Elasticsearch|elastic search|opensearch
Cassandra
DynamoDB
Snowflake
BigQuery
Kafka|apache kafka
RabbitMQ
Spark|apache spark|pyspark
Hadoop
Airflow|apache airflow
dbt
ETL|elt
Data Engineering
Data Warehousing|data warehouse
React|reactjs|react.js
Next.js|nextjs
Vue|vue.js|vuejs
Angular|angularjs
Svelte
Redux
HTML|html5
CSS|css3|sass|scss
Tailwind|tailwindcss
Node.js|nodejs|node
Express|express.js
NestJS
Django
Flask
FastAPI
Spring Boot|springboot|spring
GraphQL
REST APIs|rest api|restful|rest
gRPC
Microservices|micro-services
System Design|distributed systems
AWS|amazon web services|ec2|s3|lambda
Azure
GCP|google cloud
Docker
Kubernetes|k8s
Terraform
Ansible
Jenkins
CI/CD|cicd|continuous integration|github actions|gitlab ci
Linux|unix
Git|github|gitlab
DevOps
SRE|site reliability
Prometheus
Grafana
Datadog
Machine Learning|ml
Deep Learning
NLP|natural language processing
Computer Vision
LLM|llms|large language models
Generative AI|genai|gen ai
RAG|retrieval augmented generation
LangChain
PyTorch
TensorFlow
Keras
scikit-learn|sklearn
Pandas
NumPy
Hugging Face|huggingface|transformers
MLOps
Data Science
Data Analysis|data analytics
Statistics
A/B Testing|ab testing
Tableau
Power BI|powerbi
Looker
Excel|microsoft excel
Android
iOS
React Native
Flutter
Selenium
Cypress
Jest
Pytest|unit testing
Test Automation|automation testing
QA|quality assurance
Agile|scrum
JIRA
Product Management
Figma
UI/UX|ux design|ui design
Cybersecurity|information security|infosec
Penetration Testing|pentest
OAuth|oauth2|jwt
Blockchain|solidity|web3
Salesforce
SAP
Embedded Systems|embedded systems
Firmware
IoT
Networking|tcp/ip
Technical Writing
Project Management|pmp
Stakeholder Management
Leadership|team lead|mentoring
"""


def _build_skill_index() -> tuple[dict[str, str], re.Pattern]:
    alias_to_canon: dict[str, str] = {}
    for line in _SKILL_DEFS.strip().splitlines():
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if not parts:
            continue
        canon = parts[0]
        for a in parts:
            alias_to_canon[a.lower()] = canon
    # longest alias first so "node.js" wins over "node"
    aliases = sorted(alias_to_canon, key=len, reverse=True)
    body = "|".join(re.escape(a) for a in aliases)
    pat = re.compile(rf"(?<![A-Za-z0-9_+#])(?:{body})(?![A-Za-z0-9_+#])", re.I)
    return alias_to_canon, pat


_ALIAS_TO_CANON, _SKILL_RE = _build_skill_index()
# Words that are also ordinary English: only count them when written with a capital letter
# ("Go", "REST", "Node", "Excel", "Spring"), never plain lowercase ("the rest of the team").
_AMBIGUOUS = {"go", "rest", "node", "shell", "spring", "express", "rails", "lambda", "s3", "ec2",
              "ml", "ts", "js", "excel", "transformers", "elt", "git", "scala"}


def canonical_skill(name: str) -> str:
    n = (name or "").strip()
    return _ALIAS_TO_CANON.get(n.lower(), n)


def extract_skills(text: str | None, max_skills: int = 60) -> list[str]:
    """Skills mentioned in `text`, canonical names, in order of first appearance."""
    if not text:
        return []
    found: dict[str, int] = {}
    for m in _SKILL_RE.finditer(text):
        raw = m.group(0)
        low = raw.lower()
        if low in _AMBIGUOUS and raw == low:
            continue
        if low == "go" and re.match(r"\s+(to|ahead|live|beyond|forward|above|the)\b", text[m.end():m.end() + 10], re.I):
            continue
        canon = _ALIAS_TO_CANON.get(low)
        if canon and canon not in found:
            found[canon] = m.start()
    return sorted(found, key=found.get)[:max_skills]


# ----------------------------------------------------------------- experience

_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:\+|-|–|—|to)\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)", re.I)
_MIN_RE = re.compile(r"(?:minimum|min\.?|at least)?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)


def parse_experience(text: str | None) -> tuple[Optional[float], Optional[float]]:
    """Required years of experience from a job text: '3-5 years', '5+ years', 'at least 2 years'."""
    if not text:
        return None, None
    t = text[:6000]
    best: tuple[Optional[float], Optional[float]] = (None, None)
    for m in re.finditer(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", t, re.I):
        lo, hi = float(m.group(1)), float(m.group(2))
        if 0 <= lo <= hi <= 30:
            return lo, hi
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?\s+(?:relevant\s+|professional\s+|work\s+|industry\s+|hands[- ]on\s+)?(?:experience|exp)", t, re.I):
        lo = float(m.group(1))
        if 0 <= lo <= 30 and best[0] is None:
            best = (lo, None)
    return best


def infer_seniority(title: str | None) -> str:
    t = (title or "").lower()
    if re.search(r"\b(intern|internship|trainee|apprentice)\b", t):
        return "intern"
    if re.search(r"\b(junior|jr|graduate|entry|associate|fresher)\b", t):
        return "entry"
    if re.search(r"\b(principal|staff|director|head of|vp|distinguished)\b", t):
        return "lead"
    if re.search(r"\b(lead|manager|architect)\b", t):
        return "lead"
    if re.search(r"\b(senior|sr)\b", t) or re.search(r"\b(iii|iv)\b", t):
        return "senior"
    if re.search(r"\b(ii)\b", t):
        return "mid"
    return ""


def years_from_seniority(level: str) -> tuple[Optional[float], Optional[float]]:
    return {
        "intern": (0.0, 1.0), "entry": (0.0, 2.0), "mid": (2.0, 5.0),
        "senior": (5.0, 10.0), "lead": (8.0, None),
    }.get(level, (None, None))


_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_SPAN_RE = re.compile(
    rf"(?:(?:{_MONTHS})[a-z]*\.?\s+)?((?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*"
    rf"(?:(?:(?:{_MONTHS})[a-z]*\.?\s+)?((?:19|20)\d{{2}})|(present|current|now|till date|ongoing))",
    re.I,
)
_EXP_HEAD = re.compile(r"^\s*(work\s+)?(professional\s+)?(experience|employment|work history|career history)\b", re.I)
_END_HEAD = re.compile(r"^\s*(education|academics?|projects?|skills|technical skills|certifications?|achievements|awards|publications|extracurricular|interests)\b", re.I)


def estimate_experience_years(resume_text: str | None, now: datetime | None = None) -> Optional[float]:
    """Best-effort years of professional experience from resume text (no LLM)."""
    if not resume_text:
        return None
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:\w+\s+){0,3}?experience", resume_text, re.I)
    if m:
        v = float(m.group(1))
        if 0 < v <= 40:
            return v
    now = now or datetime.now(timezone.utc)
    in_exp = False
    spans: list[tuple[float, float]] = []
    for line in resume_text.splitlines():
        if _EXP_HEAD.match(line) and len(line) < 60:
            in_exp = True
            continue
        if in_exp and _END_HEAD.match(line) and len(line) < 60:
            in_exp = False
        if not in_exp:
            continue
        for sm in _SPAN_RE.finditer(line):
            start = float(sm.group(1))
            end = float(sm.group(2)) if sm.group(2) else now.year + now.month / 12
            if 1970 <= start <= end <= now.year + 1:
                spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    total, cur_s, cur_e = 0.0, spans[0][0], spans[0][1]
    for s, e in spans[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return round(min(total, 45.0), 1)


_TITLE_WORDS = re.compile(
    r"\b(engineer|developer|analyst|manager|scientist|designer|architect|consultant|intern|lead|"
    r"administrator|specialist|programmer|tester|officer|executive|associate)\b", re.I)


def guess_title(resume_text: str | None) -> str:
    for line in (resume_text or "").splitlines()[:15]:
        s = line.strip(" \t|•-")
        if 3 < len(s) <= 60 and _TITLE_WORDS.search(s) and "@" not in s and not re.search(r"\d{4}", s):
            return s
    return ""


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        k = i.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(i.strip())
    return out
