"""PART 4h - Mock-interview node A: scores the user's practice answer."""
from langchain_core.messages import HumanMessage, SystemMessage

from app import config
from app.llm import get_llm
from app.schemas import AnswerFeedback
from app.state import EvalState

SYSTEM = (
    "You are a tough but fair interview coach. Score the answer 1-10, list real strengths "
    "and specific improvements, check for STAR structure, and write an improved answer "
    "outline that only uses facts from the candidate's resume."
)


def answer_evaluator_node(state: EvalState) -> dict:
    llm = get_llm(temperature=0.2).with_structured_output(AnswerFeedback)
    result = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=(
            f"Company: {state.get('company_name', '')}\n"
            f"QUESTION: {state['question']}\n"
            f"CANDIDATE ANSWER: {state['user_answer']}\n"
            f"RESUME:\n{state.get('resume_text', '')[: config.MAX_RESUME_CHARS // 2]}"
        )),
    ])
    result.score = max(1, min(int(result.score), 10))
    return {"feedback": result}
