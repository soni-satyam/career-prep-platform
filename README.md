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
