"""Typed application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

LLMProvider = Literal["auto", "local", "gemini"]

# Values shipped in .env.example that must never be treated as real secrets.
_PLACEHOLDER_SECRETS = {"", "your-gemini-api-key-here", "your-langsmith-api-key-here", "changeme"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # --- LLM routing ---
    llm_provider: LLMProvider = "auto"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # --- Local (Ollama) ---
    ollama_base_url: str = "http://localhost:11434"
    default_local_model: str = "qwen2.5:7b"
    ollama_auto_install: bool = True
    ollama_auto_pull: bool = True
    ollama_startup_timeout: float = Field(default=15.0, gt=0)
    ollama_install_timeout: float = Field(default=600.0, gt=0)
    ollama_pull_timeout: float = Field(default=3600.0, gt=0)
    # First load of a 7B model on CPU can take a while.
    ollama_load_timeout: float = Field(default=180.0, gt=0)
    # How long `auto` waits for local readiness before falling back to Gemini.
    # Setup keeps running in the background, so a later call can switch to local.
    ollama_auto_fallback_timeout: float = Field(default=30.0, gt=0)

    # --- Cloud (Gemini) ---
    gemini_api_key: SecretStr | None = None
    # A "-latest" alias keeps working when Google retires pinned versions (gemini-2.5-flash was).
    gemini_model: str = "gemini-flash-lite-latest"
    # Fail fast instead of hanging on an overloaded model (HTTP 503 "high demand").
    gemini_timeout: float = Field(default=60.0, gt=0)
    gemini_max_retries: int = Field(default=2, ge=0, le=6)

    # --- Persistence ---
    # Relative paths are resolved against the backend directory.
    database_path: Path = Path("data/mental_health_agent.db")
    checkpoint_db_path: Path = Path("data/langgraph_checkpoints.db")

    # --- Observability ---
    # JSONL trace of every graph run (nodes, tool calls, routing, reflection).
    execution_log_enabled: bool = True
    execution_log_path: Path = Path("logs/execution_trace.jsonl")
    langchain_tracing_v2: bool = False
    langchain_api_key: SecretStr | None = None
    langchain_project: str = "mental-health-screening-agent"

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().lower()
            if value == "ollama":
                return "local"
        return value

    @field_validator("gemini_api_key", "langchain_api_key", mode="before")
    @classmethod
    def _drop_placeholder_secrets(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() in _PLACEHOLDER_SECRETS:
            return None
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("database_path", "checkpoint_db_path", "execution_log_path")
    @classmethod
    def _resolve_against_backend(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_DIR / value

    @property
    def gemini_configured(self) -> bool:
        return self.gemini_api_key is not None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
