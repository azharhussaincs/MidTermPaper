"""Request/response models for the system (engine status & configuration) endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProviderName = Literal["auto", "local", "gemini"]


class LLMStatus(BaseModel):
    active_provider: Literal["local", "gemini"] | None = Field(
        description="Provider new LLM calls would use right now; null if none is usable."
    )
    configured_provider: ProviderName
    ollama_installed: bool
    ollama_running: bool
    local_model_available: bool
    gemini_configured: bool
    local_model: str
    gemini_model: str
    ollama_base_url: str
    local_setup: Literal["idle", "in_progress", "ready", "failed"]
    local_setup_error: str | None


class TracingStatus(BaseModel):
    requested: bool = Field(description="LANGCHAIN_TRACING_V2 is set to true.")
    enabled: bool = Field(description="Tracing is requested and a LangSmith API key is configured.")
    project: str | None


class SystemStatus(BaseModel):
    status: Literal["ok", "degraded"] = Field(description="'degraded' when no LLM provider is usable.")
    app_env: str
    llm: LLMStatus
    tracing: TracingStatus


class LLMConfigureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: ProviderName | None = Field(None, description="New process-wide default provider.")
    local_model: str | None = Field(
        None, min_length=1, max_length=100, pattern=r"^[\w.\-:/]+$", description="e.g. qwen2.5:7b"
    )
    ensure_local: bool = Field(False, description="Re-run the Ollama install/start/pull/load check now.")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
