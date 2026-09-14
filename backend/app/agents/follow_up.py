"""PART 4i - Mock-interview node B: asks the follow-up a real interviewer would ask."""
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_llm
from app.schemas import FollowUp
from app.state import EvalState

SYSTEM = (
    "You are the interviewer. Based on the candidate's answer and its weaknesses, ask ONE "
    "sharp follow-up question that probes the weakest part."
)


def follow_up_node(state: EvalState) -> dict:
    fb = state["feedback"]
    llm = get_llm(temperature=0.5).with_structured_output(FollowUp)
    result = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=(
            f"QUESTION: {state['question']}\nANSWER: {state['user_answer']}\n"
            f"WEAKNESSES: {fb.improvements}"
        )),
    ])
    return {"follow_up": result}
