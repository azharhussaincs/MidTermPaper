"""LangGraph state for one screening session (one checkpointer thread per session)."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AssessmentGraphState(TypedDict, total=False):
    # Conversation (reducer appends / merges by message id)
    messages: Annotated[list[AnyMessage], add_messages]

    # Identity & runtime
    session_id: str  # always equal to the checkpointer thread_id
    patient_alias: str
    llm_provider: str | None  # auto | local | gemini; may change between turns

    # Metrics mirrored from SQLite after every DB write
    completion_pct: float
    missing_fields: list[str]  # "domain.field"
    inconsistencies: list[dict[str, Any]]
    risk_flags: list[dict[str, Any]]
    requires_urgent_escalation: bool
    assessment_complete: bool

    # Summary + self-reflection loop
    draft_summary: dict[str, Any] | None
    reflection_passed: bool
    reflection_feedback: str | None
    reflection_attempts: int

    # Set by an early "submit now" request: summarise with whatever has been collected
    finalize_requested: bool

    # Human-in-the-loop
    clinician_reviewed: bool
    clinician_notes: str | None
    final_output: dict[str, Any] | None

    # Safety flags raised from raw user messages (kept across turns; the DB audit only sees stored data)
    message_risk_flags: list[dict[str, Any]]
