"""ORM models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AssessmentStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    AWAITING_CLINICIAN_REVIEW = "awaiting_clinician_review"
    REVIEWED = "reviewed"
    INTERRUPTED = "interrupted"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AssessmentRecord(Base):
    """One screening conversation; `session_id` is also the LangGraph checkpointer thread_id.

    JSON columns are replaced wholesale on update (never mutated in place), so SQLAlchemy
    always detects the change.
    """

    __tablename__ = "assessment_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    patient_alias: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[AssessmentStatus] = mapped_column(
        Enum(AssessmentStatus, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e]),
        default=AssessmentStatus.IN_PROGRESS,
    )
    domain_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    missing_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    inconsistencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    clinical_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    clinician_notes: Mapped[str | None] = mapped_column(Text)
    clinician_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"AssessmentRecord(session_id={self.session_id!r}, status={self.status.value!r})"
