"""Optional Langfuse trace exporter for structured agent logs."""

from __future__ import annotations

import atexit
import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_LANGFUSE_HOST = "https://langfuse-poc.data-infra.shopee.io"
DEFAULT_LANGFUSE_FLUSH_AT_EXIT = True
DEFAULT_LANGFUSE_FLUSH_EACH_TURN = False
DEFAULT_LANGFUSE_TIMEOUT_SECONDS = 30
DEFAULT_LANGFUSE_MAX_INPUT_LEN = 100_000_000
DEFAULT_LANGFUSE_MAX_OUTPUT_LEN = 400_000_000

_client: Any | None = None
_shutdown_registered = False


@dataclass(frozen=True)
class LangfuseConfig:
    """Langfuse exporter configuration."""

    enabled: bool
    public_key: str | None
    secret_key: str | None
    host: str
    flush_at_exit: bool
    flush_each_turn: bool
    timeout_seconds: int
    max_input_len: int
    max_output_len: int


def load_langfuse_config() -> LangfuseConfig:
    """Load Langfuse settings from environment variables."""
    return LangfuseConfig(
        enabled=_env_bool("LANGFUSE_ENABLED", False),
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASE_URL")
        or DEFAULT_LANGFUSE_HOST,
        flush_at_exit=_env_bool(
            "LANGFUSE_FLUSH_AT_EXIT",
            DEFAULT_LANGFUSE_FLUSH_AT_EXIT,
        ),
        flush_each_turn=_env_bool(
            "LANGFUSE_FLUSH_EACH_TURN",
            DEFAULT_LANGFUSE_FLUSH_EACH_TURN,
        ),
        timeout_seconds=_env_int(
            "LANGFUSE_TIMEOUT",
            DEFAULT_LANGFUSE_TIMEOUT_SECONDS,
        ),
        max_input_len=_env_int(
            "LANGFUSE_MAX_INPUT_LEN",
            DEFAULT_LANGFUSE_MAX_INPUT_LEN,
        ),
        max_output_len=_env_int(
            "LANGFUSE_MAX_OUTPUT_LEN",
            DEFAULT_LANGFUSE_MAX_OUTPUT_LEN,
        ),
    )


def get_langfuse_client(config: LangfuseConfig | None = None) -> Any | None:
    """Return a shared Langfuse client, or None when tracing is disabled."""
    global _client
    global _shutdown_registered

    resolved = config or load_langfuse_config()
    if not resolved.enabled:
        return None
    if not resolved.public_key or not resolved.secret_key:
        raise RuntimeError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required.")

    if _client is None:
        try:
            from langfuse import Langfuse
        except ImportError as exc:
            raise RuntimeError(
                "Langfuse tracing is enabled but the langfuse package is not installed."
            ) from exc

        _client = Langfuse(
            public_key=resolved.public_key,
            secret_key=resolved.secret_key,
            host=resolved.host,
            timeout=resolved.timeout_seconds,
        )

    if resolved.flush_at_exit and not _shutdown_registered:
        atexit.register(shutdown_langfuse)
        _shutdown_registered = True

    return _client


def shutdown_langfuse() -> None:
    """Flush and shutdown the shared Langfuse client."""
    client = _client
    if client is None:
        return
    shutdown = getattr(client, "shutdown", None)
    if callable(shutdown):
        shutdown()
        return
    flush = getattr(client, "flush", None)
    if callable(flush):
        flush()


class LangfuseTraceExporter:
    """Exports completed turns to Langfuse when credentials are configured."""

    def __init__(self) -> None:
        self.config = load_langfuse_config()
        self.enabled = self.config.enabled
        self._client = None
        self._error: str | None = None

        if not self.enabled:
            return

        try:
            self._client = get_langfuse_client(self.config)
        except Exception as exc:
            self.enabled = False
            self._error = str(exc)

    @property
    def status(self) -> str:
        """Human-readable exporter status for startup logs."""
        if self.enabled:
            return f"enabled ({self.config.host})"
        if self._error:
            return f"disabled ({self._error})"
        return "disabled"

    def export_turn(self, *, session_id: str, turn: dict) -> None:
        """Export one completed turn as a Langfuse trace."""
        if not self.enabled or self._client is None:
            return

        try:
            root_input, root_input_meta = limit_langfuse_payload(
                {"user_input": turn.get("user_input")},
                max_len=self.config.max_input_len,
            )
            root = self._client.start_observation(
                name=f"self_assistant.turn.{turn['turn_id']}",
                as_type="agent",
                input=root_input,
                metadata={
                    "session_id": session_id,
                    "turn_id": turn.get("turn_id"),
                    "source": "self_assistant",
                    **root_input_meta,
                },
            )

            final_output: str | None = None
            for idx, step in enumerate(turn.get("steps", []), start=1):
                if step.get("type") == "LLM_CALL":
                    final_output = _export_generation(self.config, root, idx, step) or final_output
                elif step.get("type") == "TOOL_RESULT":
                    _export_tool(self.config, root, idx, step)

            root_output, root_output_meta = limit_langfuse_payload(
                {"text": final_output} if final_output else None,
                max_len=self.config.max_output_len,
            )
            root.update(output=root_output, metadata=root_output_meta or None)
            root.end()
            if self.config.flush_each_turn:
                self._client.flush()
        except Exception as exc:
            self._error = str(exc)


def _export_generation(
    config: LangfuseConfig,
    root,
    idx: int,
    step: dict,
) -> str | None:
    llm_input = step.get("input", {})
    output = step.get("output", {})
    token_usage = step.get("token_usage", {})

    input_value, input_meta = limit_langfuse_payload(
        llm_input,
        max_len=config.max_input_len,
    )
    output_value, output_meta = limit_langfuse_payload(
        output,
        max_len=config.max_output_len,
    )

    generation = root.start_observation(
        name=f"{idx:02d}-llm-call",
        as_type="generation",
        input=input_value,
        output=output_value,
        model=llm_input.get("model"),
        usage_details=_usage_details(token_usage),
        metadata={"step_index": idx, **input_meta, **output_meta},
    )
    generation.end()
    return output.get("text")


def _export_tool(config: LangfuseConfig, root, idx: int, step: dict) -> None:
    input_value, input_meta = limit_langfuse_payload(
        step.get("input"),
        max_len=config.max_input_len,
    )
    output_value, output_meta = limit_langfuse_payload(
        step.get("output"),
        max_len=config.max_output_len,
    )

    tool = root.start_observation(
        name=f"{idx:02d}-{step.get('tool_name', 'tool')}",
        as_type="tool",
        input=input_value,
        output=output_value,
        metadata={"step_index": idx, **input_meta, **output_meta},
    )
    tool.end()


def limit_langfuse_payload(value: Any, *, max_len: int) -> tuple[Any, dict[str, Any]]:
    """Truncate large payloads before sending them to Langfuse."""
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    if len(rendered) <= max_len:
        return value, {}
    return (
        rendered[:max_len],
        {
            "langfuse_payload_truncated": True,
            "langfuse_payload_original_len": len(rendered),
            "langfuse_payload_max_len": max_len,
        },
    )


def _usage_details(token_usage: dict[str, Any]) -> dict[str, int] | None:
    if not token_usage:
        return None

    usage = {}
    mapping = {
        "prompt_tokens": "input",
        "completion_tokens": "output",
        "total_tokens": "total",
        "cached_tokens": "cache_read_input_tokens",
        "thoughts_tokens": "reasoning",
    }
    for source_key, target_key in mapping.items():
        value = token_usage.get(source_key)
        if isinstance(value, int):
            usage[target_key] = value
    return usage or None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
