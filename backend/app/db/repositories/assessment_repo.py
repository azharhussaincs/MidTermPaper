"""Data access for AssessmentRecord (sync Session; callers own the transaction)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AssessmentRecord, AssessmentStatus
from app.schemas.assessment import AssessmentDomain, AssessmentDomainData, AuditReport


def get_by_session_id(db: Session, session_id: str) -> AssessmentRecord | None:
    return db.scalar(select(AssessmentRecord).where(AssessmentRecord.session_id == session_id))


def get_or_create(db: Session, session_id: str, patient_alias: str | None = None) -> AssessmentRecord:
    record = get_by_session_id(db, session_id)
    if record is None:
        record = AssessmentRecord(session_id=session_id, patient_alias=patient_alias, domain_data={})
        db.add(record)
        db.flush()
    elif patient_alias and not record.patient_alias:
        record.patient_alias = patient_alias
    return record


def list_history(
    db: Session, patient_alias: str, *, exclude_session_id: str | None = None, limit: int = 5
) -> list[AssessmentRecord]:
    query = select(AssessmentRecord).where(AssessmentRecord.patient_alias == patient_alias)
    if exclude_session_id is not None:
        query = query.where(AssessmentRecord.session_id != exclude_session_id)
    return list(db.scalars(query.order_by(AssessmentRecord.created_at.desc()).limit(limit)))


def load_domain_data(record: AssessmentRecord) -> AssessmentDomainData:
    return AssessmentDomainData.model_validate(record.domain_data or {})


def merge_domain(
    record: AssessmentRecord, domain: AssessmentDomain, updates: dict[str, Any]
) -> AssessmentDomainData:
    """Overlay `updates` (already validated, nulls removed) onto one domain; returns all data.

    Raises pydantic.ValidationError if the merged domain is invalid.
    """
    raw = dict(record.domain_data or {})
    raw[domain.value] = {**raw.get(domain.value, {}), **updates}
    data = AssessmentDomainData.model_validate(raw)
    record.domain_data = data.model_dump(mode="json", exclude_none=True)
    if record.status == AssessmentStatus.INTERRUPTED:
        record.status = AssessmentStatus.IN_PROGRESS
    return data


def save_audit(record: AssessmentRecord, report: AuditReport) -> None:
    record.missing_fields = [m.model_dump(mode="json") for m in report.missing_fields]
    record.inconsistencies = [i.model_dump(mode="json") for i in report.inconsistencies]
    record.risk_flags = [r.model_dump(mode="json") for r in report.risk_flags]
    if record.status != AssessmentStatus.REVIEWED:
        record.status = AssessmentStatus(report.completion.status)


def list_records(
    db: Session, *, statuses: list[AssessmentStatus] | None = None, limit: int = 50, offset: int = 0
) -> tuple[list[AssessmentRecord], int]:
    """Most recently updated first, with the unpaginated total."""
    query = select(AssessmentRecord)
    if statuses:
        query = query.where(AssessmentRecord.status.in_(statuses))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(AssessmentRecord.updated_at.desc()).limit(limit).offset(offset))
    return list(records), total
