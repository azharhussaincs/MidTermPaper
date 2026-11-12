"""Read models for session lists and the clinician queue (built from SQLite, no graph access)."""

from __future__ import annotations

from datetime import datetime

from app.db.models import AssessmentRecord
from app.db.repositories import assessment_repo as repo
from app.schemas.sessions import AssessmentListItem, QueueItem
from app.services import assessment_audit as audit

_RISK_RANK = {"critical": 0, "high": 1, "elevated": 2, "none": 3}


def _base_fields(record: AssessmentRecord) -> dict[str, object]:
    flags = record.risk_flags or []
    return {
        "session_id": record.session_id,
        "patient_alias": record.patient_alias,
        "status": record.status.value,
        "completion_pct": audit.completion_percentage(repo.load_domain_data(record)),
        "risk_level": audit.highest_risk_level(flags),
        "urgent": any(flag.get("requires_immediate_escalation") for flag in flags),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def to_list_item(record: AssessmentRecord) -> AssessmentListItem:
    return AssessmentListItem.model_validate(_base_fields(record))


def to_queue_item(record: AssessmentRecord) -> QueueItem:
    fields = _base_fields(record)
    return QueueItem.model_validate(
        {
            **fields,
            "early_submission": fields["completion_pct"] < 100 and not fields["urgent"],
            "top_risk_flags": [flag["code"] for flag in (record.risk_flags or [])[:3]],
            "clinician_approved": record.clinician_approved if record.status.value == "reviewed" else None,
        }
    )


def queue_priority(item: QueueItem) -> tuple[int, int, datetime]:
    """Urgent escalations first, then by highest risk level, then longest waiting first."""
    return (0 if item.urgent else 1, _RISK_RANK[item.risk_level], item.created_at)
