"""LLM provider configuration for the assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass

from google.adk.models.lite_llm import LiteLlm


COMPASS_API_BASE = "https://compass.llm.shopee.io/compass-api/v1"
DEFAULT_COMPASS_MODEL = "gemini-2.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class LlmConfig:
    """Resolved LLM settings used to construct the ADK LiteLlm wrapper."""

    provider: str
    model: str
    api_key_env: str
    api_base: str | None = None


def _prefixed_model(model: str, prefix: str) -> str:
    """Return a LiteLLM model name with the required provider prefix."""
    if "/" in model:
        return model
    return f"{prefix}/{model}"


def _get_compass_key() -> tuple[str | None, str]:
    """Read Compass key from preferred environment variables.

    OPENAI_API_KEY is supported because Compass exposes an OpenAI-compatible
    endpoint and many local shells already store the Compass key there.
    """
    for env_name in ("COMPASS_API_KEY", "OPENAI_API_KEY"):
        key = os.environ.get(env_name)
        if key:
            return key, env_name
    return None, "COMPASS_API_KEY"


def resolve_llm_config() -> LlmConfig:
    """Resolve provider/model/API settings from environment variables."""
    provider = os.environ.get("LLM_PROVIDER", "compass").strip().lower()

    if provider == "compass":
        api_key, env_name = _get_compass_key()
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_API_BASE"] = os.environ.get(
            "COMPASS_API_BASE",
            COMPASS_API_BASE,
        )

        model = os.environ.get("COMPASS_MODEL", DEFAULT_COMPASS_MODEL)
        return LlmConfig(
            provider="compass",
            model=_prefixed_model(model, "openai"),
            api_key_env=env_name,
            api_base=os.environ["OPENAI_API_BASE"],
        )

    if provider == "deepseek":
        model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
        return LlmConfig(
            provider="deepseek",
            model=_prefixed_model(model, "deepseek"),
            api_key_env="DEEPSEEK_API_KEY",
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. Use 'compass' or 'deepseek'."
    )


def create_lite_llm() -> LiteLlm:
    """Create the ADK LiteLlm instance for the selected provider."""
    config = resolve_llm_config()
    if config.provider == "compass":
        return LiteLlm(
            model=config.model,
            base_url=config.api_base,
        )
    return LiteLlm(model=config.model)
