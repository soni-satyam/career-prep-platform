"""PART 4b - Node 2: Resume + JD Analyst.

Uses a TOOL (skills.compare_skills) for hard facts, then the LLM for judgement.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app import config
from app.llm import get_llm
from app.schemas import ResumeJDAnalysis
from app.state import PrepState
from app.tools.skills import compare_skills

SYSTEM = (
    "You are an expert technical recruiter. Compare the resume against the job "
    "description honestly. Only list skills actually evidenced in the resume as matched. "
    "A keyword-scan result is provided as a factual hint; add anything it missed, "
    "but do not contradict it without a reason."
)


def analyst_node(state: PrepState) -> dict:
    resume = state["resume_text"][: config.MAX_RESUME_CHARS]
    jd = state["job_description"][: config.MAX_JD_CHARS]
    overlap = compare_skills(resume, jd)

    llm = get_llm(temperature=0.2).with_structured_output(ResumeJDAnalysis)
    prompt = (
        f"KEYWORD SCAN (tool result): {overlap}\n\n"
        f"RESUME:\n{resume}\n\nJOB DESCRIPTION:\n{jd}"
    )
    result = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
    return {"analysis": result, "keyword_overlap": overlap}
