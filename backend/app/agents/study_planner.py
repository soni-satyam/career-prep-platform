"""PART 4d - Node 4: Study Planner. Runs after the analyst, in parallel with the researcher."""
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_llm
from app.schemas import StudyPlan
from app.state import PrepState

SYSTEM = (
    "You are a career coach. Build a focused study plan (4-6 items) that closes the "
    "candidate's skill gaps for this job. Order by priority. Suggest only FREE resources "
    "by name (e.g. 'MDN Web Docs', 'freeCodeCamp', 'official docs') - never invent URLs. "
    "Each item needs one concrete practice task."
)


def study_planner_node(state: PrepState) -> dict:
    a = state["analysis"]
    llm = get_llm(temperature=0.3).with_structured_output(StudyPlan)
    prompt = (
        f"Seniority: {a.seniority_level}\n"
        f"Skill gaps: {a.skill_gaps}\n"
        f"Focus areas: {a.focus_areas}\n"
        f"Key requirements: {a.key_requirements}\n"
        f"Keyword-scan missing skills: {state.get('keyword_overlap', {}).get('missing_from_resume', [])}"
    )
    result = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
    for item in result.items:                      # clamp: LLMs ignore numeric limits
        item.estimated_hours = max(1, min(item.estimated_hours, 80))
    return {"study_plan": result}
