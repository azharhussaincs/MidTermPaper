"""Hybrid LLM engine status, runtime configuration and liveness."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError
from app.core.llm_manager import configure_llm, get_effective_settings, get_llm_status, warm_up_local_llm
from app.schemas.system import HealthResponse, LLMConfigureRequest, LLMStatus, SystemStatus, TracingStatus

router = APIRouter(prefix="/api/system", tags=["system"])


def tracing_status(settings: Settings) -> TracingStatus:
    return TracingStatus(
        requested=settings.langchain_tracing_v2,
        enabled=settings.langchain_tracing_v2 and settings.langchain_api_key is not None,
        project=settings.langchain_project if settings.langchain_tracing_v2 else None,
    )


def build_status() -> SystemStatus:
    llm = LLMStatus.model_validate(get_llm_status())
    return SystemStatus(
        status="ok" if llm.active_provider else "degraded",
        app_env=get_settings().app_env,
        llm=llm,
        tracing=tracing_status(get_settings()),
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness probe (no external calls)")
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/status", response_model=SystemStatus, summary="LLM engine, Ollama setup and tracing status")
def system_status() -> SystemStatus:
    return build_status()


@router.post(
    "/llm/configure", response_model=SystemStatus, summary="Switch provider / local model at runtime"
)
def configure_llm_engine(body: LLMConfigureRequest) -> SystemStatus:
    current = get_effective_settings()
    if body.provider == "gemini" and not current.gemini_configured:
        raise ConflictError(
            "Gemini cannot be selected: GEMINI_API_KEY is not configured on the server",
            code="gemini_not_configured",
        )

    settings = configure_llm(body.provider, body.local_model)
    changed_local = body.local_model is not None or body.provider in ("auto", "local")
    if body.ensure_local:
        warm_up_local_llm(force=True)  # explicit re-check, even if a previous run succeeded
    elif changed_local and settings.llm_provider in ("auto", "local"):
        warm_up_local_llm()  # joins an in-flight setup instead of starting a duplicate
    return build_status()
