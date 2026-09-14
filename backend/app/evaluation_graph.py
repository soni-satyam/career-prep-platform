"""PART 5c - Second graph: mock-interview practice.

The user picks a generated question, types an answer, and gets scored feedback
plus a follow-up question. It is a separate graph because it runs AFTER the
prep graph, whenever the user wants to practise.

  START --(answer too short)--> reject_answer --> END
    |
    +--> answer_evaluator --> follow_up --> END
"""
from langgraph.graph import END, START, StateGraph

from app.agents.answer_evaluator import answer_evaluator_node
from app.agents.follow_up import follow_up_node
from app.routing import route_eval_start
from app.state import EvalState


def reject_answer_node(state: EvalState) -> dict:
    return {"eval_error": "Answer is too short to evaluate. Write at least a couple of sentences."}


def build_eval_graph(checkpointer=None):
    g = StateGraph(EvalState)
    g.add_node("reject_answer", reject_answer_node)
    g.add_node("answer_evaluator", answer_evaluator_node)
    g.add_node("follow_up", follow_up_node)

    g.add_conditional_edges(
        START, route_eval_start,
        {"reject_answer": "reject_answer", "answer_evaluator": "answer_evaluator"},
    )
    g.add_edge("reject_answer", END)
    g.add_edge("answer_evaluator", "follow_up")
    g.add_edge("follow_up", END)
    return g.compile(checkpointer=checkpointer)


eval_graph = build_eval_graph()
