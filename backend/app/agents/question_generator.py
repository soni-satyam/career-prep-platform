"""PART 4e - Node 5: Question Generator.

Reads analysis + company insights. If the reviewer rejected a previous attempt,
`review_feedback` is injected so the retry fixes those exact problems.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app import config
from app.llm import get_llm
from app.schemas import QuestionSet
from app.state import PrepState

SYSTEM = """You are a senior interviewer preparing a candidate. Generate 15 questions:
- 4 technical (tied to the JD's key requirements)
- 3 behavioral (STAR-style, tied to the candidate's real experience)
- 3 company_specific (use the company research)
- 3 gap_based (probe the candidate's skill gaps - the tough ones)
- 2 role_specific
Every question must be specific to THIS candidate, role and company - no generic questions.
Each needs a 'why_asked' and an 'answer_hint' that references the candidate's own background."""


def question_generator_node(state: PrepState) -> dict:
    analysis = state["analysis"].model_dump_json(indent=2)
    company = state["company_insights"].model_dump_json(indent=2)

    prompt = (
        f"CANDIDATE vs JOB ANALYSIS:\n{analysis}\n\n"
        f"COMPANY INSIGHTS ({state['company_name']}):\n{company}\n\n"
        f"RESUME (for detail):\n{state['resume_text'][: config.MAX_RESUME_CHARS // 2]}"
    )
    feedback = state.get("review_feedback")
    if feedback:
        prompt += f"\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Fix these problems: {feedback}"

    llm = get_llm(temperature=0.5).with_structured_output(QuestionSet)
    result = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
    return {"questions": result}
