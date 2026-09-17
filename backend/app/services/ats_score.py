"""Resume ↔ job-description match score (the "ATS match meter").

Deterministic keyword coverage - no LLM call, so the number is stable and the *same* JD terms are used
for the original and the tailored resume, which is what makes "before → after" comparable.

It estimates how much of what the job asks for appears in the resume text, the way a keyword-driven
applicant tracking system screens. It is NOT any specific vendor's score.

    score = 100 * (weight of JD terms found in the resume) / (weight of all JD terms)

Weights: tech stack / hard skills 3, other keywords 2, soft skills 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from app.jobsearch.text import extract_skills

MAX_TERMS = 40

# Equivalent spellings: any form found in the resume counts for the term.
_ALIAS_GROUPS = [
    {"javascript", "js", "ecmascript"}, {"typescript", "ts"}, {"kubernetes", "k8s"},
    {"postgresql", "postgres"}, {"mongodb", "mongo"}, {"node.js", "nodejs", "node"},
    {"react", "react.js", "reactjs"}, {"vue", "vue.js", "vuejs"}, {"next.js", "nextjs"},
    {"machine learning", "ml"}, {"artificial intelligence", "ai"}, {"natural language processing", "nlp"},
    {"large language models", "large language model", "llm", "llms"}, {"generative ai", "genai", "gen ai"},
    {"ci/cd", "cicd", "ci cd", "continuous integration"}, {"amazon web services", "aws"},
    {"google cloud", "gcp", "google cloud platform"}, {"golang", "go"}, {"c#", "csharp"}, {".net", "dotnet"},
    {"rest", "restful", "rest api", "rest apis", "restful apis"}, {"graphql", "graph ql"},
    {"object oriented", "object-oriented", "oop"}, {"unit testing", "unit tests", "unit test"},
    {"sql", "structured query language"}, {"nosql", "no sql"}, {"scikit-learn", "sklearn", "scikit learn"},
]
_ALIASES: dict[str, set[str]] = {}
for _g in _ALIAS_GROUPS:
    for _w in _g:
        _ALIASES[_w] = _g

_STOP = {"and", "or", "of", "the", "a", "an", "to", "in", "for", "with", "on", "using", "experience", "strong",
         "knowledge", "skills", "skill", "ability", "good", "excellent", "working", "understanding", "proficiency"}

# Words in a requirement that carry no signal on their own.
_GENERIC = {"team", "work", "teams", "role", "company", "business", "years", "year"}


@dataclass(frozen=True)
class Term:
    label: str
    weight: int


def _norm(text: str) -> str:
    t = (text or "").lower().replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", t)


def _has(text: str, phrase: str) -> bool:
    p = re.escape(phrase)
    return re.search(rf"(?<![a-z0-9+#.]){p}(?:s|es)?(?![a-z0-9+#])", text) is not None


def _tokens(phrase: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9+#.]+", phrase.lower()) if w and w not in _STOP and w not in _GENERIC]


def term_matches(text: str, label: str) -> bool:
    """`text` must already be passed through _norm()."""
    key = _norm(label).strip(" .,;:")
    if not key:
        return False
    forms = _ALIASES.get(key, {key})
    if any(_has(text, f) for f in forms):
        return True
    toks = _tokens(key)
    # a multi-word requirement ("distributed systems design") counts when all its meaningful words appear
    if len(toks) >= 2:
        words = set(re.split(r"[^a-z0-9+#.]+", text))
        return all(t in words or t.rstrip("s") in words or (t + "s") in words for t in toks)
    return False


def _iter_str(v: Any) -> Iterable[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _iter_str(x)


def build_terms(jd_analysis: Optional[dict[str, Any]], jd_text: str = "") -> list[Term]:
    """Weighted, de-duplicated list of what the JD asks for."""
    jd = jd_analysis or {}
    weighted: list[tuple[str, int]] = []
    for s in _iter_str([jd.get("tech_stack"), jd.get("hard_skills")]):
        weighted.append((s, 3))
    for s in _iter_str(jd.get("keywords")):
        weighted.append((s, 2))
    for s in _iter_str(jd.get("soft_skills")):
        weighted.append((s, 1))
    if len(weighted) < 5:  # analysis missing / thin -> fall back to the skills named in the JD itself
        for s in extract_skills(jd_text, max_skills=30):
            weighted.append((s, 3))

    seen: dict[str, Term] = {}
    for label, w in weighted:
        label = re.sub(r"\s+", " ", str(label)).strip(" .,;:")
        if not label or len(label) > 60:
            continue
        k = _norm(label)
        canon = min(_ALIASES.get(k, {k}))      # "js" and "javascript" are one term
        if canon not in seen or w > seen[canon].weight:
            seen[canon] = Term(label if canon == k else label, w)
    terms = sorted(seen.values(), key=lambda t: -t.weight)
    return terms[:MAX_TERMS]


def resume_to_text(resume: dict[str, Any]) -> str:
    """Flatten a tailored-resume dict (contracts.TailoredResume shape) to plain text."""
    parts: list[str] = []
    p = resume.get("profile") or {}
    parts += [str(p.get(k) or "") for k in ("name", "school")]
    parts.append(str(resume.get("summary") or ""))
    parts.append(", ".join(str(s) for s in resume.get("skills") or []))
    for key in ("experience", "projects", "awards"):
        for it in resume.get(key) or []:
            if isinstance(it, dict):
                parts += [str(it.get("title") or ""), str(it.get("content") or "")]
            else:
                parts.append(str(it))
    for ed in resume.get("education") or []:
        if isinstance(ed, dict):
            parts.append(" ".join(str(ed.get(k) or "") for k in ("school", "degree", "major")))
    return "\n".join(x for x in parts if x)


def score_resume(resume_text: str, terms: list[Term]) -> dict[str, Any]:
    text = _norm(resume_text)
    total = sum(t.weight for t in terms)
    matched = [t.label for t in terms if term_matches(text, t.label)]
    missing = [t.label for t in terms if t.label not in set(matched)]
    got = sum(t.weight for t in terms if t.label in set(matched))
    return {
        "score": round(100 * got / total) if total else 0,
        "matched": matched,
        "missing": missing,
        "total_terms": len(terms),
    }


def compare(original_text: str | None, tailored: dict[str, Any] | None,
            jd_analysis: Optional[dict[str, Any]], jd_text: str = "") -> Optional[dict[str, Any]]:
    """{"before": {...}|None, "after": {...}, "delta": int|None, "gained": [...], "still_missing": [...]}"""
    terms = build_terms(jd_analysis, jd_text)
    if not terms or not tailored:
        return None
    after = score_resume(resume_to_text(tailored), terms)
    before = score_resume(original_text, terms) if (original_text or "").strip() else None
    return _assemble(before, after, terms)


def _assemble(before: Optional[dict[str, Any]], after: dict[str, Any], terms: list[Term]) -> dict[str, Any]:
    gained = [t for t in after["matched"] if before and t not in set(before["matched"])]
    return {
        "before": before,
        "after": after,
        "delta": (after["score"] - before["score"]) if before else None,
        "gained": gained,
        "still_missing": after["missing"],
        # kept so an edited resume can be re-scored against the SAME requirements, without the JD
        "terms": [{"label": t.label, "weight": t.weight} for t in terms],
        "method": "keyword coverage of the job description's skills and requirements",
    }


def rescore(match: dict[str, Any], tailored: dict[str, Any]) -> dict[str, Any]:
    """Re-score an edited tailored resume against the stored terms; the 'before' score never changes."""
    terms = [Term(str(t["label"]), int(t["weight"])) for t in match.get("terms") or []]
    return _assemble(match.get("before"), score_resume(resume_to_text(tailored), terms), terms)


def unverified_skills(original_text: str | None, tailored: dict[str, Any]) -> list[str]:
    """Skills the tailored resume lists that never appear in the candidate's original resume.

    The tailoring model must not invent skills, but it can over-reach; this is the check that tells
    the candidate exactly what to confirm (or delete) before sending the resume to a recruiter.
    """
    text = _norm(original_text or "")
    if not text.strip():
        return []
    out = []
    for sk in tailored.get("skills") or []:
        sk = str(sk).strip()
        if sk and not term_matches(text, sk):
            out.append(sk)
    return out
