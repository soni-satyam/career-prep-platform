"""One explainable "how ready is this resume for this job" verdict.

The gap agent's readiness label is an LLM opinion and can disagree with the measured keyword match
(e.g. "ready" at 30%). The verdict shown to the user is the more cautious of the two, and the factors
that produced it are returned so the UI can show *why*.
"""

from __future__ import annotations

from typing import Any, Optional

LEVELS = ["significant_gap", "needs_work", "almost", "ready"]  # worst -> best

COPY = {
    "ready": ("Ready to apply", "Your resume covers what this job asks for."),
    "almost": ("Almost there", "Most requirements are covered. A few gaps are worth closing first."),
    "needs_work": ("Needs work", "Important requirements are missing or weak. Fix the high-priority gaps before applying."),
    "significant_gap": ("Significant gaps", "This role asks for a lot your resume does not show yet. Consider building these skills first."),
}


def _by_score(score: int) -> int:
    return 3 if score >= 75 else 2 if score >= 60 else 1 if score >= 40 else 0


def verdict(match: Optional[dict[str, Any]], gaps: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    gaps = gaps or {}
    items = [g for g in gaps.get("gaps") or [] if isinstance(g, dict)]
    counts = {k: sum(1 for g in items if g.get("severity") == k) for k in ("high", "medium", "low")}
    llm = gaps.get("overall_readiness") if gaps.get("overall_readiness") in LEVELS else None

    if not match and not llm:
        return None

    ranks = []
    factors: list[dict[str, str]] = []
    if match:
        score = int(match["after"]["score"])
        ranks.append(_by_score(score))
        factors.append({"tone": "good" if score >= 75 else "ok" if score >= 50 else "bad",
                        "text": f"{score}% of the job's skills and requirements appear in your tailored resume"})
        if match.get("delta") is not None and match["delta"] != 0:
            factors.append({"tone": "good" if match["delta"] > 0 else "bad",
                            "text": f"Tailoring {'raised' if match['delta'] > 0 else 'lowered'} the match by {abs(match['delta'])} points"})
    if counts["high"]:
        ranks.append(1 if counts["high"] >= 3 else 2)   # any high-priority gap means not yet "ready"
        factors.append({"tone": "bad", "text": f"{counts['high']} high-priority gap{'s' if counts['high'] != 1 else ''} to address"})
    elif items:
        factors.append({"tone": "ok", "text": f"{len(items)} smaller gap{'s' if len(items) != 1 else ''} to consider"})
    else:
        factors.append({"tone": "good", "text": "No gaps were flagged against your experience"})
    if llm is not None:
        ranks.append(LEVELS.index(llm))

    level = LEVELS[min(ranks)]
    label, headline = COPY[level]
    return {"level": level, "label": label, "headline": headline, "factors": factors, "counts": counts,
            "ai_assessment": llm}
