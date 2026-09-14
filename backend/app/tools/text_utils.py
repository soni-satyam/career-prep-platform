"""PART 3c - Cheap deterministic text helpers (no LLM needed)."""
import re

_SECTION_PATTERNS = {
    "experience": r"\b(experience|employment|work history)\b",
    "education": r"\b(education|academic)\b",
    "skills": r"\b(skills|technologies|tech stack)\b",
    "projects": r"\bprojects?\b",
}
_JD_HINTS = ["responsibilit", "requirement", "qualification", "you will",
             "we are looking", "experience with", "preferred", "about the role"]


def clean_text(text: str) -> str:
    text = (text or "").replace("\x00", "").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_sections(text: str) -> list[str]:
    low = text.lower()
    return [name for name, pat in _SECTION_PATTERNS.items() if re.search(pat, low)]


def looks_like_resume(text: str) -> bool:
    return len(detect_sections(text)) >= 2


def looks_like_job_description(text: str) -> bool:
    low = text.lower()
    return sum(h in low for h in _JD_HINTS) >= 2
