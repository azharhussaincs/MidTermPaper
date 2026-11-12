"""The 4 assessment tools the agent calls.

Design rules for reliable tool calling on both Gemini and Ollama:
- `session_id` is an `InjectedToolArg`: hidden from the model's schema and always supplied
  by the graph from the LangGraph thread, so a model can never read or write another session.
- Every tool has an explicit `args_schema`; `domain` is an enum, so the model sees the
  allowed values (common paraphrases are still accepted).
- Tools never raise on bad model input. They return `{"ok": false, "error": ...}` with
  enough detail (allowed fields, validation messages) for the model to correct itself.
- Outputs are plain JSON-serialisable dicts.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.tools import BaseTool, InjectedToolArg, tool
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.db.database import get_session
from app.db.models import AssessmentRecord
from app.db.repositories import assessment_repo as repo
from app.questionnaires.guides import get_domain_guide
from app.schemas.assessment import (
    DOMAIN_MODELS,
    REQUIRED_FIELDS,
    AssessmentDomain,
    AssessmentDomainData,
    AssessmentRecordRead,
    AuditReport,
    CompletionStatus,
    parse_domain,
)
from app.services import assessment_audit as audit


def _describe_domain_fields() -> str:
    lines = []
    for domain, model in DOMAIN_MODELS.items():
        fields = ", ".join(model.model_fields)
        lines.append(f"- {domain.value}: {fields}")
    return "\n".join(lines)


SESSION_ID_FIELD = Field(
    min_length=1, max_length=128, description="Injected by the graph; never model-supplied."
)
SessionId = Annotated[str, InjectedToolArg]


# A Literal (not the StrEnum) keeps the enum inline: Gemini's converter ignores `$defs`.
DomainName = Literal["mood", "stress", "sleep", "anxiety", "functioning", "concerns"]


class _DomainArg(BaseModel):
    domain: DomainName = Field(description="Which of the 6 screening domains.")

    @field_validator("domain", mode="before")
    @classmethod
    def _lenient_domain(cls, value: object) -> object:
        return parse_domain(value).value if isinstance(value, str) else value


class StoreAssessmentResponseArgs(_DomainArg):
    session_id: SessionId = SESSION_ID_FIELD
    data: dict[str, Any] = Field(
        description="Field/value pairs for this domain only. Use the exact field names from "
        "get_screening_questionnaire_guide. Omit fields the user has not answered. Allowed fields:\n"
        + _describe_domain_fields()
    )


class RetrieveAssessmentRecordArgs(BaseModel):
    session_id: SessionId = SESSION_ID_FIELD
    patient_alias: str | None = Field(
        None, max_length=128, description="Anonymised alias; used to find earlier assessments."
    )


class ValidateAndAuditArgs(BaseModel):
    session_id: SessionId = SESSION_ID_FIELD


class QuestionnaireGuideArgs(_DomainArg):
    pass


def _error(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": message, **extra}


def _completion(data: AssessmentDomainData, status: str) -> CompletionStatus:
    return audit.completion_status(data, status)


def _history_entry(record: AssessmentRecord) -> dict[str, Any]:
    data = repo.load_domain_data(record)
    return {
        "session_id": record.session_id,
        "status": record.status.value,
        "created_at": record.created_at.isoformat(),
        "completion_percentage": audit.completion_percentage(data),
        "risk_flags": [{"code": f["code"], "level": f["level"]} for f in record.risk_flags or []],
        "clinical_summary": record.clinical_summary,
        "clinician_approved": record.clinician_approved,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(args_schema=StoreAssessmentResponseArgs)
def store_assessment_response(session_id: str, domain: DomainName, data: dict[str, Any]) -> dict[str, Any]:
    """Save the user's answers for ONE screening domain and get the updated completion percentage.

    Call this right after the user answers, with only the fields they actually answered.
    Answers are merged into what was already saved for this session; re-sending a field
    overwrites it. If the result has ok=false, fix the listed fields and call again.
    """
    domain_enum = AssessmentDomain(domain)
    model = DOMAIN_MODELS[domain_enum]
    try:
        validated = model.model_validate(data)
    except ValidationError as exc:
        return _error(
            f"Invalid data for domain '{domain}'",
            errors=[
                {"field": ".".join(map(str, e["loc"])) or "data", "message": e["msg"]} for e in exc.errors()
            ],
            allowed_fields=list(model.model_fields),
        )
    updates = validated.model_dump(exclude_none=True)
    if not updates:
        return _error("No answered fields were provided", allowed_fields=list(model.model_fields))

    with get_session() as db:
        record = repo.get_or_create(db, session_id)
        merged = repo.merge_domain(record, domain_enum, updates)
        completion = _completion(merged, record.status.value)

    domain_model = merged.domain(domain_enum)
    missing_here = [f for f in REQUIRED_FIELDS[domain_enum] if getattr(domain_model, f) in (None, [], "")]
    return {
        "ok": True,
        "session_id": session_id,
        "domain": domain,
        "stored_fields": sorted(updates),
        "domain_complete": not missing_here,
        "missing_required_in_domain": missing_here,
        "completion_percentage": completion.percentage,
        "pending_domains": [d.value for d in completion.pending_domains],
    }


@tool(args_schema=RetrieveAssessmentRecordArgs)
def retrieve_assessment_record(session_id: str, patient_alias: str | None = None) -> dict[str, Any]:
    """Fetch the current session's saved assessment plus this person's earlier assessments.

    Use at the start of a conversation (to resume or for continuity with past screenings)
    and before writing the final summary. `patient_alias` finds history when the current
    session has no alias yet.
    """
    with get_session() as db:
        record = repo.get_by_session_id(db, session_id)
        alias = patient_alias or (record.patient_alias if record else None)
        if record is not None and patient_alias and not record.patient_alias:
            record.patient_alias = patient_alias
        history = repo.list_history(db, alias, exclude_session_id=session_id) if alias else []

        current = None
        if record is not None:
            data = repo.load_domain_data(record)
            current = AssessmentRecordRead.model_validate(record).model_dump(mode="json")
            current["completion"] = _completion(data, record.status.value).model_dump(mode="json")

        return {
            "ok": True,
            "found": record is not None,
            "current": current,
            "history": [_history_entry(r) for r in history],
        }


@tool(args_schema=ValidateAndAuditArgs)
def validate_and_audit_responses(session_id: str) -> dict[str, Any]:
    """Check all saved answers for missing required fields, contradictions and risk indicators.

    Call after each domain is finished and always before the final summary. If
    `requires_immediate_escalation` is true, stop the screening and follow the safety
    protocol. Ask the user gently about any listed inconsistencies or missing fields.
    """
    with get_session() as db:
        record = repo.get_by_session_id(db, session_id)
        if record is None:
            return _error(f"No assessment has been saved for session '{session_id}' yet")

        data = repo.load_domain_data(record)
        missing = audit.missing_fields(data)
        flags = audit.find_risk_flags(data)
        status = "awaiting_clinician_review" if not missing else "in_progress"
        if record.status.value == "reviewed":
            status = "reviewed"
        report = AuditReport(
            session_id=session_id,
            completion=_completion(data, status),
            missing_fields=missing,
            inconsistencies=audit.find_inconsistencies(data),
            risk_flags=flags,
            requires_immediate_escalation=any(f.requires_immediate_escalation for f in flags),
            requires_professional_review=bool(flags) or not missing,
        )
        repo.save_audit(record, report)

    return {"ok": True, **report.model_dump(mode="json")}


@tool(args_schema=QuestionnaireGuideArgs)
def get_screening_questionnaire_guide(domain: DomainName) -> dict[str, Any]:
    """Get the structured, non-diagnostic questions to ask for one screening domain.

    Returns the opening line, each question with the exact `field` name and answer format
    to use with store_assessment_response, and the guardrails to follow. Ask the questions
    one at a time, in your own warm words.
    """
    return {"ok": True, **get_domain_guide(AssessmentDomain(domain))}


ASSESSMENT_TOOLS: list[BaseTool] = [
    store_assessment_response,
    retrieve_assessment_record,
    validate_and_audit_responses,
    get_screening_questionnaire_guide,
]
