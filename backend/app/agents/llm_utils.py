"""Shared helpers for agent LLM calls with JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any, Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.llm import get_chat_model

T = TypeVar("T", bound=BaseModel)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_json_response(content: str | Any) -> dict[str, Any]:
    if not isinstance(content, str):
        content = str(content)
    text = _strip_fences(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to find first { ... }
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"raw_response": content, "error": "Failed to parse JSON"}


async def run_json_agent(
    system: str,
    user: str,
    schema: Type[T] | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Call the configured LLM and return parsed JSON (optionally validated)."""
    llm = get_chat_model(temperature=temperature)
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user),
    ]
    response = await llm.ainvoke(messages)
    data = parse_json_response(response.content)

    if schema is not None and "error" not in data:
        try:
            return schema.model_validate(data).model_dump()
        except Exception:
            # return raw parsed data if validation fails
            return data
    return data
