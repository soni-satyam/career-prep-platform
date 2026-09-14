"""PART 3e - Free Wikipedia lookup (no API key)."""
import httpx

_HEADERS = {"User-Agent": "CareerPrepAgents/0.1 (learning project)"}


def wikipedia_summary(name: str) -> tuple[str, str]:
    """Returns (summary_text, page_url). ('','') if nothing found. Never raises."""
    try:
        with httpx.Client(timeout=8, headers=_HEADERS) as c:
            r = c.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": name, "limit": 1, "format": "json"},
            )
            titles = r.json()[1]
            if not titles:
                return "", ""
            title = titles[0].replace(" ", "_")
            s = c.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}")
            data = s.json()
            return data.get("extract", ""), data.get("content_urls", {}).get("desktop", {}).get("page", "")
    except Exception:
        return "", ""
