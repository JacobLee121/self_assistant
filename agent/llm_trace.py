"""Capture ADK LLM request snapshots for structured logging."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_current_turn_requests: list[dict] = []


def clear_llm_requests() -> None:
    """Clear captured LLM request snapshots for the current turn."""
    _current_turn_requests.clear()


def consume_llm_requests() -> list[dict]:
    """Return captured request snapshots and clear the buffer."""
    snapshots = deepcopy(_current_turn_requests)
    clear_llm_requests()
    return snapshots


def capture_llm_request(llm_request) -> None:
    """Capture the full model input from an ADK LlmRequest."""
    config = llm_request.config
    config_payload = _to_jsonable(config)
    if isinstance(config_payload, dict):
        system_instruction = config_payload.pop("systemInstruction", None)
        tools = config_payload.pop("tools", None)
    else:
        system_instruction = None
        tools = None
        config_payload = {}

    _current_turn_requests.append({
        "model": llm_request.model,
        "system_instruction": system_instruction,
        "contents": [_to_jsonable(content) for content in llm_request.contents],
        "tools": tools or [],
        "generation_config": config_payload,
    })


def _to_jsonable(obj: Any) -> Any:
    """Convert ADK/GenAI objects into JSON-compatible values."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude_unset=True,
        )
    return str(obj)
