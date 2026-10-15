# CareerPrep

AI-powered career preparation platform inspired by AI Career Copilot.

Paste a JD + your resume → get **JD analysis**, **profile extraction**, **gap analysis**, **tailored resume**, **interview Q&A**, and a **multi-week preparation plan**.

Built for **free LLM providers** (Gemini primary, Groq secondary).

## Features (ported & adapted from AI Career Copilot)

| Feature | Endpoint / UI |
|---------|----------------|
| JD Analysis | `POST /api/v1/prep/analyze-jd` |
| Profile Extraction | `POST /api/v1/prep/extract-profile` |
| Gap Analysis | `POST /api/v1/prep/analyze-gaps` |
| Resume Tailoring | `POST /api/v1/prep/tailor-resume` + **Resume** page |
| Interview Q&A Pack | `POST /api/v1/prep/interview-pack` + **Interview Prep** page |
| Full pipeline | `POST /api/v1/prep/sessions` (runs all agents) |
| Auth (email + Google + GitHub) | `/signin`, `/signup` |
| Admin panel | `/admin` (feature flags, users) |

## Stack

- **Frontend**: React + TypeScript + Vite + Tailwind
- **Backend**: FastAPI + multi-agent (LangChain)
- **DB**: PostgreSQL 16 + pgvector
- **Cache**: Redis
- **LLM**: Gemini (free) / Groq (free) / OpenAI
- **Deploy**: Docker Compose

## Quick Start

```bash
cp .env.example .env
# Add at least:
# GOOGLE_API_KEY=...   (https://aistudio.google.com/apikey)

cd frontend && npm install && cd ..
docker compose up --build
```

- App: http://localhost:5173  
- API docs: http://localhost:8001/docs  

### Default admin

```
Email:    admin@careerprep.local
Password: admin12345
```

## Company search

`GET /api/v1/companies/lookup?q=<name or website>` identifies a company and returns a short, evidence-based
intro (what it does, founded, headquarters), its career page and the other job portals to browse.
`GET /api/v1/companies/jobs?name=...&website=...` then returns every job we can find for it, with the same
filters as `/jobs/search`. Behind the second call, in order:

1. the company's own career page (JSON-LD `JobPosting`, embedded JSON, or job links followed to their pages);
2. its ATS board (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee), found from the career page,
   or guessed from the company name and verified against the postings (so startups work too);
3. your configured aggregators (JSearch / Adzuna / Jooble), narrowed to that company;
4. job pages on LinkedIn / Naukri / Indeed / Wellfound found through web search (no direct scraping of those sites).

Optional settings: `COMPANY_CACHE_TTL_SECONDS`, `COMPANY_LOOKUP_TIMEOUT_SECONDS`, `COMPANY_CAREER_BUDGET_SECONDS`,
`COMPANY_WEB_SEARCH_ENABLED`. Controlled by the existing `company_search` feature flag. Pages that only render
their job list with JavaScript can't be read; the UI says so and links to the page. Outbound fetches only
go to public http(s) hosts (private/loopback/metadata addresses are refused, including after redirects).

## Auth

- **Email/password** — works out of the box
- **Google / GitHub OAuth** — set `GOOGLE_CLIENT_*` and `GITHUB_CLIENT_*` in `.env`

## Agent pipeline

```
JD text ──► JD Agent ──► structured JD analysis
Resume  ──► Profile Agent ──► candidate profile + facts
                │
                ▼
         Gap Agent ──► gaps + strengths + readiness
                │
                ▼
      Resume Agent ──► tailored resume (STAR, JD-ordered skills)
                │
                ▼
   Interview Agent ──► 8+ Q&As (technical / project / behavioral)
                │
                ▼
         Plan Agent ──► multi-week preparation plan + resume tips
```

All agents return structured JSON and are callable individually or via the full session pipeline.
