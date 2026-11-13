"""FastAPI application: lifespan (DB, checkpointer, graph, background Ollama setup), CORS, routers.

Run from the backend directory:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ROUTERS
from app.core.config import get_settings
from app.core.exceptions import UnhandledErrorMiddleware, register_exception_handlers
from app.core.execution_logger import configure_langsmith
from app.core.llm_manager import get_effective_settings, warm_up_local_llm
from app.core.logging_config import setup_logging
from app.db.checkpointer import close_checkpointer, create_checkpointer
from app.db.database import dispose_db, init_db
from app.graph import nodes
from app.graph.workflow import build_graph, set_graph

logger = logging.getLogger(__name__)

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

OPENAPI_TAGS = [
    {"name": "system", "description": "Hybrid LLM engine status and runtime configuration."},
    {"name": "assessments", "description": "Patient intake sessions and conversational screening."},
    {"name": "clinician", "description": "Human-in-the-loop review queue and sign-off."},
]


def create_app(
    *,
    llm_factory: nodes.LLMFactory | None = None,
    db_path: str | Path | None = None,
    checkpoint_path: str | Path | None = None,
    warm_up_local: bool = True,
) -> FastAPI:
    """App factory. Tests pass a scripted `llm_factory` and temporary database paths."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging(settings.log_level)
        configure_langsmith(settings)
        init_db(db_path)
        checkpointer = create_checkpointer(checkpoint_path)
        app.state.graph = build_graph(llm_factory, checkpointer)
        set_graph(app.state.graph)

        # Non-blocking: install/start/pull/load runs on a daemon thread; the server is up
        # immediately and /api/system/status reports progress ("local_setup").
        if warm_up_local and get_effective_settings().llm_provider in ("auto", "local"):
            warm_up_local_llm()
            logger.info("Local Ollama setup started in the background")

        logger.info("API ready")
        try:
            yield
        finally:
            set_graph(None)
            close_checkpointer(checkpointer)
            dispose_db()
            logger.info("API shut down cleanly")

    app = FastAPI(
        title="Mental Health Screening Agent API",
        version="0.1.0",
        description="Non-diagnostic intake screening agent (LangGraph) with clinician review. "
        "Outputs organise self-reported information and are never a diagnosis.",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    # Added first = innermost: errors become JSON *before* CORS headers are applied.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted({*DEV_ORIGINS, *settings.cors_origin_list}),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    return app


app = create_app()
