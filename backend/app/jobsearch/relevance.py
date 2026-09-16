"""Title-first relevance for role searches.

Rules (see tests/test_job_relevance.py):
  1. Title relevance wins: "AI Engineer" outranks a generic "Software Engineer".
  2. A role search is gated on the TITLE. A passing mention of AI / Python / ML in the
     description never lets an unrelated title through.
  3. Related titles stay: "Machine Learning Engineer", "Applied AI Engineer",
     "Generative AI Engineer" are relevant to "AI Engineer", just ranked below exact hits.

A query is split into
  * role nouns   (engineer, developer, scientist ...)  -> must be compatible with the title's noun
  * modifiers    (senior, lead, junior ...)            -> never required, small ranking bonus
  * domain terms (ai, backend, data, devops ...)       -> must appear in the title (directly or via a
                                                          related-concept family)
  * skill terms  (python, java ...)                    -> satisfied by the title OR a whole-word
                                                          mention in the description
Queries with no role noun ("kubernetes", "python") are keyword searches: title or description.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Relevance tiers (lower = more relevant). Used for ranking.
EXACT, STRONG, RELATED, KEYWORD = 0, 1, 2, 3

_STOP = {"a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "jobs", "job", "role", "roles",
         "position", "positions", "opening", "openings", "hiring"}

# ---- role nouns: groups of interchangeable job-title nouns -------------------------------------
_NOUN_GROUPS: list[set[str]] = [
    {"engineer", "developer", "programmer", "swe", "sde", "dev", "devs", "engineering", "development"},
    {"scientist", "researcher", "research"},
    {"analyst", "analytics"},
    {"architect"},
    {"manager", "mgr", "head", "director"},
    {"designer"},
    {"consultant"},
    {"administrator", "admin"},
    {"specialist"},
    {"intern", "trainee"},
]
_NOUN_GROUP_OF: dict[str, int] = {w: i for i, g in enumerate(_NOUN_GROUPS) for w in g}
# only these *words* count as the head noun; "engineering"/"development" etc. are too ambiguous
# ("Engineering Manager" is a manager, not an engineer) and are handled by the manager group winning.
_PRIORITY_GROUP = 4  # manager/director beats engineer when both appear ("Engineering Manager")

_MODIFIERS = {"senior", "sr", "junior", "jr", "lead", "staff", "principal", "associate", "entry", "mid", "i", "ii", "iii"}
_MOD_CANON = {"sr": "senior", "jr": "junior"}

# ---- domain concepts: query term -> family of title phrases that satisfy it --------------------
# Every phrase is matched as whole words inside the normalised title.
_CONCEPTS: dict[str, dict[str, list[str]]] = {
    # concept: {"exact": phrases that ARE this concept, "related": near-equivalents}
    "ai": {
        "exact": ["ai", "artificial intelligence"],
        "related": ["ml", "machine learning", "genai", "gen ai", "generative ai", "llm", "deep learning",
                    "nlp", "applied ai", "applied ml", "computer vision", "mlops", "ai ml", "ml ai"],
    },
    "ml": {
        "exact": ["ml", "machine learning"],
        "related": ["ai", "artificial intelligence", "deep learning", "genai", "generative ai", "llm", "nlp",
                    "applied ai", "applied ml", "computer vision", "mlops"],
    },
    "genai": {
        "exact": ["genai", "gen ai", "generative ai"],
        "related": ["llm", "ai", "artificial intelligence", "ml", "machine learning", "applied ai"],
    },
    "llm": {
        "exact": ["llm"],
        "related": ["genai", "generative ai", "ai", "nlp", "ml", "machine learning", "applied ai"],
    },
    "nlp": {"exact": ["nlp", "natural language processing"], "related": ["ml", "machine learning", "ai", "llm"]},
    "data": {"exact": ["data"], "related": ["analytics", "bi", "business intelligence"]},
    "backend": {"exact": ["backend", "back end", "server side"], "related": ["api", "platform"]},
    "frontend": {"exact": ["frontend", "front end", "ui"], "related": ["web", "react", "angular", "vue"]},
    "fullstack": {"exact": ["fullstack", "full stack"], "related": []},
    "devops": {"exact": ["devops", "dev ops"], "related": ["sre", "site reliability", "platform", "infrastructure", "cloud"]},
    "sre": {"exact": ["sre", "site reliability"], "related": ["devops", "platform", "infrastructure"]},
    "cloud": {"exact": ["cloud"], "related": ["devops", "infrastructure", "platform"]},
    "security": {"exact": ["security", "cybersecurity", "infosec"], "related": ["appsec", "devsecops"]},
    "mobile": {"exact": ["mobile"], "related": ["android", "ios"]},
    "android": {"exact": ["android"], "related": ["mobile"]},
    "ios": {"exact": ["ios"], "related": ["mobile"]},
    "qa": {"exact": ["qa", "quality assurance", "test", "testing", "sdet"], "related": ["automation"]},
}

# canonical spelling of query tokens before concept lookup
_ALIASES = {
    "front": "frontend", "back": "backend", "full": "fullstack", "gpt": "llm", "llms": "llm",
    "a.i.": "ai", "m.l.": "ml", "data-science": "data", "datascience": "data",
}

# Languages / tools that may legitimately be satisfied by the description.
_SKILL_TERMS = {
    "python", "java", "javascript", "typescript", "golang", "go", "rust", "c++", "c#", "csharp", ".net", "dotnet",
    "kotlin", "swift", "ruby", "rails", "php", "scala", "react", "angular", "vue", "node", "nodejs", "django",
    "flask", "fastapi", "spring", "aws", "azure", "gcp", "kubernetes", "docker", "sql", "postgres", "mongodb",
    "terraform", "pytorch", "tensorflow", "spark", "kafka", "langchain",
}

_SPLIT = re.compile(r"[^a-z0-9+#.]+")


def _words(text: str | None) -> list[str]:
    t = (text or "").lower().replace("&", " and ").replace("/", " ").replace("-", " ")
    t = re.sub(r"\bmachine\s+learning\b", "ml", t)
    t = re.sub(r"\bartificial\s+intelligence\b", "ai", t)
    t = re.sub(r"\bnatural\s+language\s+processing\b", "nlp", t)
    t = re.sub(r"\bfull\s+stack\b", "fullstack", t)
    t = re.sub(r"\bfront\s+end\b", "frontend", t)
    t = re.sub(r"\bback\s+end\b", "backend", t)
    t = re.sub(r"\bgen\s+ai\b", "genai", t)
    t = re.sub(r"\bgenerative\s+ai\b", "generative ai", t)
    t = re.sub(r"\bsite\s+reliability\b", "site reliability", t)
    t = re.sub(r"\bdev\s+ops\b", "devops", t)
    out = [w.strip(".") for w in _SPLIT.split(t)]
    return [w for w in out if w]


def _phrase_in(phrase: str, words: list[str]) -> bool:
    p = _words(phrase)
    n = len(p)
    if not n:
        return False
    return any(words[i:i + n] == p for i in range(len(words) - n + 1))


def _any_phrase(phrases: list[str], words: list[str]) -> bool:
    return any(_phrase_in(p, words) for p in phrases)


def _whole_word(term: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9+#]){re.escape(term)}(?![a-z0-9+#])", text) is not None


def _head_group(words: list[str]) -> Optional[int]:
    """Which role-noun group the title is about (manager/director beats engineer)."""
    groups = {_NOUN_GROUP_OF[w] for w in words if w in _NOUN_GROUP_OF}
    if not groups:
        return None
    if _PRIORITY_GROUP in groups:
        return _PRIORITY_GROUP
    # "Engineer" is only the head if no weaker noun is present, e.g. "Sales Engineer" is still an engineer,
    # which is acceptable; "Engineering Manager" was handled above.
    return min(groups)


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    nouns: tuple[str, ...]
    noun_groups: frozenset[int]
    modifiers: tuple[str, ...]
    concepts: tuple[str, ...]        # known domain concepts
    plain: tuple[str, ...]           # other domain words that must be in the title
    skills: tuple[str, ...]          # title-or-description terms

    @property
    def is_role_query(self) -> bool:
        return bool(self.noun_groups)

    @property
    def empty(self) -> bool:
        return not (self.nouns or self.concepts or self.plain or self.skills or self.modifiers)


def parse_query(q: str) -> ParsedQuery:
    nouns: list[str] = []
    mods: list[str] = []
    concepts: list[str] = []
    plain: list[str] = []
    skills: list[str] = []
    for w in _words(q):
        if w in _STOP:
            continue
        w = _ALIASES.get(w, w)
        if w in _MODIFIERS:
            mods.append(_MOD_CANON.get(w, w))
        elif w in _NOUN_GROUP_OF:
            nouns.append(w)
        elif w in _CONCEPTS:
            concepts.append(w)
        elif w in _SKILL_TERMS:
            skills.append(w)
        else:
            plain.append(w)
    # "engineering manager" is a manager role, not an engineer role: same head-noun rule as titles
    head = _head_group(nouns)
    groups = frozenset({head}) if head is not None else frozenset()
    return ParsedQuery(q, tuple(nouns), groups, tuple(mods), tuple(dict.fromkeys(concepts)),
                       tuple(dict.fromkeys(plain)), tuple(dict.fromkeys(skills)))


@dataclass(frozen=True)
class Relevance:
    tier: int          # EXACT | STRONG | RELATED | KEYWORD
    score: int         # 0-100, higher is better; 0 never returned (job is rejected instead)


def score_title(query: str | ParsedQuery, title: str, description: str = "") -> Optional[Relevance]:
    """None = reject. Otherwise how relevant the posting is to the searched role."""
    pq = query if isinstance(query, ParsedQuery) else parse_query(query)
    if pq.empty:
        return Relevance(KEYWORD, 50)

    tw = _words(title)
    tset = set(tw)
    desc = (description or "").lower()[:6000]

    # ---------- keyword search (no role noun, e.g. "python", "kubernetes", "react") -------------
    if not pq.is_role_query:
        terms = list(pq.concepts) + list(pq.plain) + list(pq.skills)
        if not terms:
            return Relevance(KEYWORD, 50)
        in_title = all(t in tset or _concept_hit(t, tw) is not None for t in terms)
        if in_title:
            return Relevance(STRONG, 85)
        if all(t in tset or _concept_hit(t, tw) is not None or _whole_word(t, desc) for t in terms):
            return Relevance(KEYWORD, 40)
        return None

    # ---------- role search: noun must be compatible, domain must be in the TITLE ---------------
    head = _head_group(tw)
    if head is None or head not in pq.noun_groups:
        return None

    tier = EXACT
    for c in pq.concepts:
        hit = _concept_hit(c, tw)
        if hit is None:
            return None
        tier = max(tier, hit)
    for p in pq.plain:
        if p not in tset:
            return None
    for s in pq.skills:
        if s in tset:
            continue
        if not _whole_word(s, desc):
            return None

    # phrase bonus: the query's domain words appear contiguously / in order in the title
    domain = [w for w in _words(pq.raw) if w not in _STOP and w not in _MODIFIERS and w not in _NOUN_GROUP_OF]
    exact_phrase = bool(domain) and _phrase_in(" ".join(domain), tw)
    if tier == EXACT and not exact_phrase and (pq.concepts or pq.plain):
        tier = STRONG

    score = {EXACT: 95, STRONG: 85, RELATED: 65}[tier]
    # seniority modifier asked for and present -> small bonus
    if pq.modifiers and any(m in {_MOD_CANON.get(w, w) for w in tw} for m in pq.modifiers):
        score = min(100, score + 3)
    # exact role noun (not just the same group) is a hair better
    if any(n in tset for n in pq.nouns):
        score = min(100, score + 2)
    # tie-break: "AI Engineer" beats "Applied AI Engineer Platform Infrastructure" at the same tier
    extra = max(0, len(tw) - len(domain) - len(pq.nouns) - len(pq.modifiers))
    score = max(1, score - min(extra, 6))
    return Relevance(tier, score)


def _concept_hit(concept: str, title_words: list[str]) -> Optional[int]:
    """EXACT if the title names the concept, RELATED if it names a family member, None otherwise."""
    fam = _CONCEPTS.get(concept)
    if fam is None:
        return EXACT if concept in set(title_words) else None
    if _any_phrase(fam["exact"], title_words):
        return EXACT
    if _any_phrase(fam["related"], title_words):
        return RELATED
    return None


def query_matches_job(query: str, title: str, description: str = "") -> bool:
    return score_title(query, title, description) is not None
