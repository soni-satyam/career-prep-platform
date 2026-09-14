# Career Prep Agents - Backend

Resume + JD + company name -> tailored interview prep, via LangGraph agents, served by FastAPI.
Free stack: Groq/Gemini free tier, DuckDuckGo, Wikipedia, SQLite.

## Setup
    python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env         # add a free Groq or Gemini key
    uvicorn app.main:app --reload
    # interactive docs: http://localhost:8001/docs

## Test without any API key (fake LLM)
    cd tests && python test_graph_offline.py && python test_api_offline.py

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | multipart: `job_description`, `company_name`, and `resume_file` (pdf/docx/txt) OR `resume_text`. Returns `202 {session_id}` immediately |
| GET | `/api/sessions/{id}/events` | **SSE** progress: one event per finished node; ends with `done` / `failed` / `rejected`. Supports `Last-Event-ID` |
| GET | `/api/sessions/{id}` | status + final report (when `completed`) |
| POST | `/api/sessions/{id}/practice` | `{question_id, answer, follow_up_question?}` -> score, feedback, follow-up |
| GET | `/api/sessions/{id}/practice` | practice history |
| DELETE | `/api/sessions/{id}` | delete resume, report, history |
| GET | `/api/graph` | nodes/edges, to draw a live progress diagram |
| GET | `/health` | provider + whether a key is configured |

### Try it with curl
    curl -X POST localhost:8001/api/sessions -F company_name="Stripe" \
         -F job_description="$(cat jd.txt)" -F resume_file=@resume.pdf
    curl -N localhost:8001/api/sessions/<id>/events
    curl localhost:8001/api/sessions/<id>
    curl -X POST localhost:8001/api/sessions/<id>/practice -H 'content-type: application/json' \
         -d '{"question_id":"behavioral-1","answer":"In my last project I ..."}'

### Session lifecycle
`pending -> running -> completed | failed | rejected` (rejected = unusable input).

### For the React + TypeScript app later
- Types: `npx openapi-typescript http://localhost:8001/openapi.json -o api.d.ts`
- Progress: `new EventSource('/api/sessions/<id>/events')`, listen for `node`, `done`, `failed`, `rejected`
- Allowed origins are set by `CORS_ORIGINS` in `.env` (Vite/CRA ports by default)

## Design notes
- **Background runs:** POST returns instantly; the graph runs as an asyncio task. Events and the report are stored in SQLite, so a page refresh or SSE reconnect loses nothing.
- **Free-tier protection:** `MAX_CONCURRENT_RUNS` caps parallel graph runs, per-IP rate limits cap abuse, `RUN_TIMEOUT_SECONDS` stops runaway runs, and provider errors are mapped to friendly messages (raw errors are never returned).
- **Privacy:** resumes live in `data/career_prep.db`, are never returned by the API, are deleted on `DELETE`, and are auto-purged after `RETENTION_DAYS`. Session ids are unguessable but there is no login - add auth before sharing publicly.
- **Restarts:** runs interrupted by a restart are marked `failed` on startup.
- **Single process:** rate limits and the concurrency cap are in-memory, so run ONE uvicorn worker (add `--proxy-headers` behind a proxy).

## Code map (read in this order)
config.py, llm.py -> schemas.py, state.py -> tools/ -> agents/ -> routing.py -> graph.py, evaluation_graph.py
-> db.py, api_models.py, services.py (graph <-> DB glue) -> routes.py -> main.py
