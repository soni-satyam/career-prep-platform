"""PART 7d - The glue between the LangGraph graphs and the database.

run_prep_session():  runs the prep graph in the background, saving one event per finished
                     node (the SSE endpoint replays these) and the final report at the end.
run_practice():      runs the mock-interview graph for one answer.
"""
import asyncio
import logging

from app import config, db
from app.evaluation_graph import eval_graph
from app.graph import career_graph

log = logging.getLogger("career_prep")

# Limits how many graph runs hit the LLM at once (free tiers rate-limit hard).
_semaphore: asyncio.Semaphore | None = None
_tasks: set[asyncio.Task] = set()      # strong refs so background tasks aren't garbage-collected


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_RUNS)
    return _semaphore


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def friendly_error(exc: Exception) -> str:
    """Never leak raw provider errors (they can contain request details)."""
    text = f"{type(exc).__name__} {exc}".lower()
    if "429" in text or "rate" in text or "quota" in text or "resource_exhausted" in text:
        return "The AI provider's free-tier limit was hit. Wait a minute and try again."
    if "401" in text or "403" in text or "api key" in text or "authentication" in text or "permission" in text:
        return "The AI provider rejected the server's API key. Check the backend configuration."
    return "Something went wrong while generating your prep. Please try again."


def summarize(node: str, update: dict) -> str:
    u = update or {}
    if node == "input_validator":
        return u.get("validation_error") or "Inputs validated"
    if node == "analyst" and u.get("analysis"):
        a = u["analysis"]
        return f"Resume analysed: {len(a.matched_skills)} matched skills, {len(a.skill_gaps)} gaps"
    if node == "company_researcher" and u.get("company_insights"):
        return f"Company researched ({len(u['company_insights'].sources)} sources)"
    if node == "study_planner" and u.get("study_plan"):
        return f"Study plan ready ({len(u['study_plan'].items)} topics)"
    if node == "question_generator" and u.get("questions"):
        return f"Drafted {len(u['questions'].questions)} questions"
    if node == "quality_reviewer" and u.get("review"):
        r = u["review"]
        return "Questions approved" if r.approved else f"Questions rejected, retrying: {'; '.join(r.issues)[:200]}"
    if node == "report_builder":
        return "Final report assembled"
    return f"{node} finished"


async def run_prep_session(session_id: str) -> None:
    async with _sem():
        s = db.get_session(session_id, private=True)
        if not s:
            return
        db.update_session(session_id, status="running")
        db.add_event(session_id, "status", message="Run started")

        inputs = {
            "resume_text": s["resume_text"],
            "job_description": s["job_description"],
            "company_name": s["company_name"],
            "errors": [],
        }
        result: dict = {}

        async def consume():
            async for step in career_graph.astream(inputs, stream_mode="updates"):
                for node, update in step.items():
                    update = update or {}
                    db.add_event(session_id, "node", node=node, message=summarize(node, update))
                    if "final_report" in update:
                        result["report"] = update["final_report"]
                    if "validation_error" in update:
                        result["rejected"] = update["validation_error"]

        try:
            await asyncio.wait_for(consume(), timeout=config.RUN_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            _fail(session_id, "The run took too long and was stopped. Please try again.")
            return
        except Exception as exc:
            log.exception("prep session %s failed", session_id)
            _fail(session_id, friendly_error(exc))
            return

        if result.get("rejected"):
            db.add_event(session_id, "rejected", message=result["rejected"])
            db.update_session(session_id, status="rejected", error=result["rejected"])
        elif result.get("report"):
            db.update_session(session_id, status="completed", report=result["report"])
            db.add_event(session_id, "done", message="Your prep is ready")
        else:
            _fail(session_id, "The run finished without producing a report.")


def _fail(session_id: str, message: str) -> None:
    # event first, status last: the SSE loop stops once it sees a terminal status
    db.add_event(session_id, "failed", message=message)
    db.update_session(session_id, status="failed", error=message)


async def run_practice(session: dict, question: str, answer: str):
    """Returns the EvalState dict. Raises asyncio.TimeoutError / provider errors to the caller."""
    async with _sem():
        return await asyncio.wait_for(
            eval_graph.ainvoke({
                "question": question,
                "user_answer": answer,
                "resume_text": session["resume_text"],
                "company_name": session["company_name"],
            }),
            timeout=config.RUN_TIMEOUT_SECONDS,
        )
