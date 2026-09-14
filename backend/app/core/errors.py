"""Safe error helpers — never leak stack traces or secrets to clients."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("careerprep")

# Status → default public message
PUBLIC_DEFAULTS = {
    400: "Something was wrong with that request. Please check your input.",
    401: "Please sign in again to continue.",
    403: "You don't have permission to do that.",
    404: "We couldn't find what you were looking for.",
    409: "That already exists. Try something different.",
    422: "Please check the form and try again.",
    429: "Too many requests. Please wait a moment.",
    500: "Something went wrong. Please try again later.",
    502: "The AI service is temporarily unavailable. Please try again.",
    503: "Service temporarily unavailable. Please try again later.",
}

# Short phrases we allow through from intentional HTTPException(detail=...)
SAFE_PHRASES = (
    "invalid email",
    "incorrect email or password",
    "email already registered",
    "not authenticated",
    "not found",
    "inactive",
    "disabled",
    "empty file",
    "unsupported file",
    "could not extract",
    "no tailored resume",
    "google oauth is not configured",
    "github oauth is not configured",
    "could not get email",
    "missing",
    "password",
    "feature",
)


def public_detail(status: int, detail: object) -> str:
    text = ""
    if isinstance(detail, str):
        text = detail.strip()
    elif isinstance(detail, list):
        # validation errors — keep generic
        return PUBLIC_DEFAULTS.get(422, PUBLIC_DEFAULTS[400])
    else:
        text = str(detail) if detail is not None else ""

    lower = text.lower()
    if not text or len(text) > 160:
        return PUBLIC_DEFAULTS.get(status, PUBLIC_DEFAULTS[500])
    if any(x in lower for x in ("traceback", "exception", "api_key", "secret", "bearer ")):
        return PUBLIC_DEFAULTS.get(status, PUBLIC_DEFAULTS[500])
    if status >= 500:
        # Never expose internal 5xx text
        return PUBLIC_DEFAULTS.get(status, PUBLIC_DEFAULTS[500])
    if any(p in lower for p in SAFE_PHRASES):
        return text
    # intentional short product messages under 4xx
    if status < 500 and len(text) < 120 and "\n" not in text:
        return text
    return PUBLIC_DEFAULTS.get(status, PUBLIC_DEFAULTS[500])


def llm_http_error(exc: Exception) -> tuple[int, str]:
    """Map LLM / agent failures to a safe (status, detail)."""
    msg = str(exc).lower()
    if isinstance(exc, ValueError):
        # often missing API key
        if "api" in msg and "key" in msg:
            return 502, PUBLIC_DEFAULTS[502]
        return 400, PUBLIC_DEFAULTS[400]
    return 502, PUBLIC_DEFAULTS[502]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": public_detail(exc.status_code, exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.info("validation error on %s: %s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": PUBLIC_DEFAULTS[422]},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": PUBLIC_DEFAULTS[500]},
        )
