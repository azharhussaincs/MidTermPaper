"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph

from app.core.exceptions import NotFoundError
from app.db.database import get_session
from app.db.repositories import assessment_repo as repo


def get_graph(request: Request) -> CompiledStateGraph:
    """The compiled graph created by the app lifespan (shares its checkpointer)."""
    return request.app.state.graph


GraphDep = Annotated[CompiledStateGraph, Depends(get_graph)]


def require_session(session_id: str) -> str:
    """Path dependency: 404 unless the assessment exists."""
    with get_session() as db:
        if repo.get_by_session_id(db, session_id) is None:
            raise NotFoundError(f"Assessment session '{session_id}' not found", code="session_not_found")
    return session_id


SessionIdDep = Annotated[str, Depends(require_session)]
