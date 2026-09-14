"""PART 3d - Deterministic skill matcher (a TOOL the analyst calls).

Why: LLMs sometimes hallucinate "matched" skills. This gives the analyst
hard facts to ground on. Extend SKILL_VOCAB for your target roles.
"""
import re

SKILL_VOCAB = [
    # languages
    "python", "java", "javascript", "typescript", "c++", "c#", "golang", "rust", "kotlin",
    "swift", "scala", "php", "ruby", "sql", "bash", "matlab",
    # web
    "react", "next.js", "node.js", "express", "angular", "vue", "html", "css", "tailwind",
    "django", "flask", "fastapi", "spring", "graphql", "rest",
    # data / ml / ai
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras", "spark", "hadoop",
    "airflow", "dbt", "tableau", "power bi", "machine learning", "deep learning", "nlp",
    "computer vision", "llm", "langchain", "langgraph", "rag", "mlops", "statistics",
    "data analysis", "data engineering", "etl",
    # databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "snowflake", "bigquery",
    "dynamodb", "kafka",
    # cloud / devops
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins", "ci/cd",
    "github actions", "linux", "git", "microservices", "system design",
    # practices
    "agile", "scrum", "jira", "unit testing", "tdd", "code review", "leadership",
]


def _pattern(term: str) -> re.Pattern:
    # lookarounds instead of \b so "c++", "c#", "node.js" match correctly
    return re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(term)}(?![A-Za-z0-9+#])", re.IGNORECASE)


def extract_skills(text: str) -> set[str]:
    return {t for t in SKILL_VOCAB if _pattern(t).search(text or "")}


def compare_skills(resume_text: str, jd_text: str) -> dict:
    resume, jd = extract_skills(resume_text), extract_skills(jd_text)
    return {
        "matched": sorted(resume & jd),
        "missing_from_resume": sorted(jd - resume),
        "extra_in_resume": sorted(resume - jd),
    }
