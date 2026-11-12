"""Patient intake: start a session, chat, submit early, and read session state."""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import GraphDep, SessionIdDep
from app.db.database import get_session
from app.db.models import AssessmentStatus
from app.db.repositories import assessment_repo as repo
from app.graph import workflow
from app.schemas.sessions import (
    AssessmentDetail,
    AssessmentListResponse,
    AssessmentStatusName,
    AssessmentTurnResponse,
    SendMessageRequest,
    StartAssessmentRequest,
)
from app.services.assessment_views import to_list_item

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


@router.post(
    "/start",
    response_model=AssessmentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a session and seed the greeting",
)
def start_assessment(body: StartAssessmentRequest, graph: GraphDep) -> AssessmentDetail:
    session_id = f"sess_{uuid.uuid4().hex}"
    alias = body.patient_alias or f"anon-{secrets.token_hex(3)}"
    state = workflow.start_session(session_id, alias, body.llm_provider, graph=graph)
    return AssessmentDetail.model_validate(state)


@router.post("/{session_id}/message", response_model=AssessmentTurnResponse, summary="Send one user message")
def send_message(
    session_id: SessionIdDep, body: SendMessageRequest, graph: GraphDep
) -> AssessmentTurnResponse:
    result = workflow.run_assessment_turn(
        session_id, body.message, llm_provider=body.llm_provider, graph=graph
    )
    return AssessmentTurnResponse.model_validate(result)


@router.post(
    "/{session_id}/finalize",
    response_model=AssessmentTurnResponse,
    summary="Submit early: summarise partial answers and queue for clinician review",
)
def finalize_assessment(session_id: SessionIdDep, graph: GraphDep) -> AssessmentTurnResponse:
    return AssessmentTurnResponse.model_validate(workflow.finalize_session(session_id, graph=graph))


@router.get("/{session_id}", response_model=AssessmentDetail, summary="Full session state and chat history")
def get_assessment(session_id: SessionIdDep, graph: GraphDep) -> AssessmentDetail:
    return AssessmentDetail.model_validate(workflow.get_session_state(session_id, graph=graph))


@router.get("", response_model=AssessmentListResponse, summary="List sessions (most recently updated first)")
def list_assessments(
    status_filter: Annotated[list[AssessmentStatusName] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssessmentListResponse:
    statuses = [AssessmentStatus(s) for s in status_filter] if status_filter else None
    with get_session() as db:
        records, total = repo.list_records(db, statuses=statuses, limit=limit, offset=offset)
        return AssessmentListResponse(items=[to_list_item(r) for r in records], total=total)
