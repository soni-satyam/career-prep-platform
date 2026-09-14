"""PART 4c - Node 3: Company Researcher. (Uses 3 TOOLS: search, Wikipedia, page fetch.)

Pattern: gather evidence with tools -> LLM summarises ONLY that evidence.
Every tool fails soft, so a bad network never crashes the graph.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_llm
from app.schemas import CompanyInsights
from app.state import PrepState
from app.tools.page_fetcher import fetch_page_text
from app.tools.web_search import format_results, search_web
from app.tools.wikipedia import wikipedia_summary

SYSTEM = (
    "You summarize company research for interview prep. Use ONLY the evidence given. "
    "If something is not in it, leave it empty or say 'unknown'. Never invent facts."
)


def company_researcher_node(state: PrepState) -> dict:
    company = state["company_name"]
    sources: list[str] = []
    evidence = ""

    # Tool 1: Wikipedia
    wiki_text, wiki_url = wikipedia_summary(company)
    if wiki_text:
        evidence += f"\n## Wikipedia\n{wiki_text}"
        sources.append(wiki_url)

    # Tool 2: web search (several angles)
    overview_results: list[dict] = []
    for i, q in enumerate([
        f"{company} company overview products",
        f"{company} company culture values",
        f"{company} latest news",
        f"{company} interview process questions",
    ]):
        results = search_web(q, 4)
        if i == 0:
            overview_results = results
        evidence += f"\n## Search: {q}\n{format_results(results)}"
        sources += [r["href"] for r in results[:2] if r.get("href")]

    # Tool 3: read the top overview page in full
    if overview_results and overview_results[0].get("href"):
        page = fetch_page_text(overview_results[0]["href"])
        if page:
            evidence += f"\n## Page text ({overview_results[0]['href']})\n{page}"

    errors = []
    if len(evidence.strip()) < 50:
        errors.append("No company evidence found online; insights will be thin.")

    llm = get_llm(temperature=0.2).with_structured_output(CompanyInsights)
    result = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=f"Company: {company}\n\nEVIDENCE:{evidence}"),
    ])
    result.sources = list(dict.fromkeys(sources))[:8]   # de-duplicate, keep order
    return {"company_insights": result, "errors": errors}
