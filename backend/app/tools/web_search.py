"""PART 3b - Free web search via DuckDuckGo (no API key)."""
try:
    from ddgs import DDGS
except ImportError:  # older package name
    from duckduckgo_search import DDGS


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Returns [{'title','href','body'}]. Never raises - search is best effort."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


def format_results(results: list[dict]) -> str:
    return "\n".join(f"- {r.get('title','')}: {r.get('body','')}" for r in results)
