"""PART 3f - Fetch a web page and return readable text."""
import httpx
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CareerPrepAgents/0.1)"}


def fetch_page_text(url: str, max_chars: int = 3000) -> str:
    """Best effort. Returns '' on any failure. URLs come from our own search results."""
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=8, follow_redirects=True)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:max_chars]
    except Exception:
        return ""
