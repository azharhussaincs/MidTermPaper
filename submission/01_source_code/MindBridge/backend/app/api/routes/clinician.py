"""Human-in-the-loop: the clinician review queue and sign-off."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep, SessionIdDep
from app.db.database import get_session
from app.db.models import AssessmentStatus
from app.db.repositories import assessment_repo as repo
from app.graph import workflow
from app.schemas.sessions import ClinicianQueueResponse, ClinicianReviewRequest, ClinicianReviewResponse
from app.services.assessment_views import queue_priority, to_queue_item

router = APIRouter(prefix="/api/clinician", tags=["clinician"])


@router.get(
    "/queue", response_model=ClinicianQueueResponse, summary="Awaiting review (urgent first) + recent"
)
def clinician_queue(reviewed_limit: Annotated[int, Query(ge=0, le=100)] = 20) -> ClinicianQueueResponse:
    with get_session() as db:
        awaiting, _ = repo.list_records(db, statuses=[AssessmentStatus.AWAITING_CLINICIAN_REVIEW], limit=1000)
        reviewed, _ = repo.list_records(db, statuses=[AssessmentStatus.REVIEWED], limit=reviewed_limit)
        return ClinicianQueueResponse(
            awaiting_review=sorted((to_queue_item(r) for r in awaiting), key=queue_priority),
            recently_reviewed=[to_queue_item(r) for r in reviewed],
        )


@router.post(
    "/{session_id}/review",
    response_model=ClinicianReviewResponse,
    summary="Approve/annotate a summary and resume the paused graph",
)
def submit_review(
    session_id: SessionIdDep, body: ClinicianReviewRequest, graph: GraphDep
) -> ClinicianReviewResponse:
    state = workflow.submit_clinician_review(
        session_id, body.approved, body.clinician_notes, body.revised_summary, graph=graph
    )
    final = state["final_output"]
    return ClinicianReviewResponse(
        session_id=session_id,
        status=state["status"],
        clinician_approved=final["clinician_approved"],
        clinician_notes=final["clinician_notes"],
        reviewed_at=final["reviewed_at"],
        urgent=final["urgent"],
        early_submission=final["early_submission"],
        summary_revised_by_clinician=final["summary_revised_by_clinician"],
        summary=final["summary"],
        ai_draft_summary=final["ai_draft_summary"],
    )
