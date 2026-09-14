"""PART 4g - Node 7: Report Builder (NO LLM). Assembles everything into one clean result."""
from collections import defaultdict

from app.state import PrepState

CATEGORY_TITLES = {
    "technical": "Technical",
    "behavioral": "Behavioral",
    "company_specific": "Company-specific",
    "gap_based": "Gap-based (tough ones)",
    "role_specific": "Role-specific",
}


def report_builder_node(state: PrepState) -> dict:
    a, c = state["analysis"], state["company_insights"]
    plan, review = state["study_plan"], state["review"]
    warnings = list(state.get("errors", []))
    if not review.approved:
        warnings.append(f"Reviewer still had concerns after retries: {review.issues}")

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for q in state["questions"].questions:
        d = q.model_dump()
        d["id"] = f"{q.category}-{len(by_cat[q.category]) + 1}"   # stable id used by the practice API
        by_cat[q.category].append(d)

    md = [f"# Interview prep: {state['company_name']}", "", "## Candidate snapshot",
          a.candidate_summary, f"\n**Level:** {a.seniority_level}",
          f"\n**Matched skills:** {', '.join(a.matched_skills) or '-'}",
          f"\n**Gaps:** {', '.join(a.skill_gaps) or '-'}", "", "## Company snapshot", c.overview]
    if c.interview_style and c.interview_style.lower() != "unknown":
        md.append(f"\n**Interview style:** {c.interview_style}")
    md += ["", "## Study plan", plan.summary, ""]
    for it in plan.items:
        md.append(f"- **{it.topic}** [{it.priority}, ~{it.estimated_hours}h]: {it.why} "
                  f"Practice: {it.practice_task} (Resources: {', '.join(it.free_resources)})")
    md += ["", "## Questions"]
    for cat, title in CATEGORY_TITLES.items():
        if cat in by_cat:
            md += ["", f"### {title}"]
            for i, q in enumerate(by_cat[cat], 1):
                md += [f"{i}. **{q['question']}**",
                       f"   - Why asked: {q['why_asked']}",
                       f"   - Hint: {q['answer_hint']}"]
    if warnings:
        md += ["", "## Warnings"] + [f"- {w}" for w in warnings]

    return {"final_report": {
        "markdown": "\n".join(md),
        "analysis": a.model_dump(),
        "company_insights": c.model_dump(),
        "study_plan": plan.model_dump(),
        "questions_by_category": dict(by_cat),
        "review": review.model_dump(),
        "warnings": warnings,
    }}
