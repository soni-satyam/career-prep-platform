"""PART 5b - The main LangGraph. This is the heart of the project.

  START -> input_validator --(invalid)--> END
                 |
                 +--(valid, parallel)--> analyst ---------> study_planner --+
                 |                                                          +--> question_generator
                 +--------------------> company_researcher -----------------+          |   ^
                                                                                       v   | (rejected,
                                                                                quality_reviewer  retry)
                                                                                       |
                                                                              (approved) v
                                                                                 report_builder -> END
"""
from langgraph.graph import END, START, StateGraph

from app.agents.analyst import analyst_node
from app.agents.company_researcher import company_researcher_node
from app.agents.input_validator import input_validator_node
from app.agents.question_generator import question_generator_node
from app.agents.quality_reviewer import quality_reviewer_node
from app.agents.report_builder import report_builder_node
from app.agents.study_planner import study_planner_node
from app.routing import route_after_review, route_after_validation
from app.state import PrepState


def build_graph(checkpointer=None):
    g = StateGraph(PrepState)

    g.add_node("input_validator", input_validator_node)
    g.add_node("analyst", analyst_node)
    g.add_node("company_researcher", company_researcher_node)
    g.add_node("study_planner", study_planner_node)
    g.add_node("question_generator", question_generator_node)
    g.add_node("quality_reviewer", quality_reviewer_node)
    g.add_node("report_builder", report_builder_node)

    g.add_edge(START, "input_validator")

    # conditional fan-out (or stop on bad input)
    g.add_conditional_edges(
        "input_validator",
        route_after_validation,
        {"analyst": "analyst", "company_researcher": "company_researcher", END: END},
    )

    g.add_edge("analyst", "study_planner")
    # fan-in: generator waits for BOTH the planner chain and the researcher
    g.add_edge(["study_planner", "company_researcher"], "question_generator")

    g.add_edge("question_generator", "quality_reviewer")
    # the agentic loop
    g.add_conditional_edges(
        "quality_reviewer",
        route_after_review,
        {"question_generator": "question_generator", "report_builder": "report_builder"},
    )
    g.add_edge("report_builder", END)

    return g.compile(checkpointer=checkpointer)


career_graph = build_graph()
