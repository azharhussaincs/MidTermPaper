"""Request/response models for the assessment (patient) and clinician endpoints."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.assessment import AssessmentSummaryOutput, Inconsistency, RiskFlag
from app.schemas.system import ProviderName

#: Anonymous patient codes: letters, digits, '-' or '_', 3-32 characters (a digit is also required).
ALIAS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,31}")
ALIAS_RULE = (
    "Use an anonymous code with at least one number, such as anon-417 or blue-28, not your name. "
    "Letters, numbers, '-' and '_' only, 3 to 32 characters."
)

AssessmentStatusName = Literal["in_progress", "awaiting_clinician_review", "reviewed", "interrupted"]
RiskLevel = Literal["critical", "high", "elevated", "none"]


class _UTCModel(BaseModel):
    """SQLite drops tz info; every datetime we return is UTC."""

    @field_validator("*", mode="after")
    @classmethod
    def _assume_utc(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class StartAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    patient_alias: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        description="Anonymous code with at least one number (e.g. anon-417); generated if omitted. Never a real name.",
    )
    llm_provider: ProviderName | None = Field(None, description="Override the engine for this session.")

    @field_validator("patient_alias")
    @classmethod
    def _anonymous_code(cls, value: str | None) -> str | None:
        """Guard against real names: a code of 3-32 letters, digits, '-' or '_', with at least one digit.

        A plain word ("Azhar") or a full name ("Sam Lee") is rejected, so a person cannot be
        identified by the alias shown to clinicians and stored with their answers.
        """
        if value is None or value == "":
            return None
        if not ALIAS_PATTERN.fullmatch(value) or not any(c.isdigit() for c in value):
            raise ValueError(ALIAS_RULE)
        return value


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)
    llm_provider: ProviderName | None = None


class ClinicianReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    approved: bool
    clinician_notes: str = Field(min_length=1, max_length=10_000)
    revised_summary: AssessmentSummaryOutput | None = Field(
        None,
        description="Clinician-edited summary that replaces the AI draft (disclaimer is always enforced).",
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class DomainProgress(BaseModel):
    completed: bool
    answered: int
    required: int
    percentage: float


class ChatMessage(_UTCModel):
    id: str | None = None
    created_at: datetime | None = None
    role: str = Field(description="user | assistant | tool")
    content: str
    tool_calls: list[str] | None = None
    name: str | None = None


class AssessmentTurnResponse(BaseModel):
    session_id: str
    accepted: bool = Field(description="False when the message was not processed (e.g. review pending).")
    reply: str
    replies: list[str]
    status: AssessmentStatusName | None
    completion_pct: float
    domain_completion_map: dict[str, DomainProgress]
    missing_fields: list[str]
    inconsistencies: list[Inconsistency]
    risk_flags: list[RiskFlag]
    requires_urgent_escalation: bool
    assessment_complete: bool
    awaiting_clinician_review: bool
    draft_summary: dict[str, Any] | None
    final_output: dict[str, Any] | None = None


class AssessmentDetail(AssessmentTurnResponse, _UTCModel):
    patient_alias: str | None
    llm_provider: ProviderName | None
    messages: list[ChatMessage]
    domain_data: dict[str, Any]
    clinical_summary: dict[str, Any] | None
    pending_review: dict[str, Any] | None
    reflection_passed: bool | None
    reflection_attempts: int
    reflection_feedback: str | None
    finalize_requested: bool
    clinician_reviewed: bool
    clinician_notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


class AssessmentListItem(_UTCModel):
    session_id: str
    patient_alias: str | None
    status: AssessmentStatusName
    completion_pct: float
    risk_level: RiskLevel
    urgent: bool
    created_at: datetime
    updated_at: datetime


class AssessmentListResponse(BaseModel):
    items: list[AssessmentListItem]
    total: int


class QueueItem(AssessmentListItem):
    early_submission: bool = Field(description="Submitted before all required fields were answered.")
    top_risk_flags: list[str]
    clinician_approved: bool | None


class ClinicianQueueResponse(BaseModel):
    awaiting_review: list[QueueItem] = Field(
        description="Urgent first, then by risk level, then oldest first."
    )
    recently_reviewed: list[QueueItem]


class ClinicianReviewResponse(_UTCModel):
    session_id: str
    status: AssessmentStatusName
    clinician_approved: bool
    clinician_notes: str | None
    reviewed_at: datetime
    urgent: bool
    early_submission: bool
    summary_revised_by_clinician: bool
    summary: AssessmentSummaryOutput
    ai_draft_summary: dict[str, Any] | None
