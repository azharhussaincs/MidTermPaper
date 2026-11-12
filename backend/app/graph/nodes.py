"""Graph nodes and routing functions.

Safety-relevant decisions are deterministic and never depend on an LLM:
- every raw user message is scanned for self-harm / harm-to-others language,
- escalation, pause and crisis messages are fixed text,
- the reflection step checks diagnostic language and audit coverage with rules first and
  only then asks an LLM reviewer for a second opinion.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import interrupt

from app.core.llm_manager import get_llm
from app.db.database import get_session
from app.db.models import AssessmentRecord, AssessmentStatus
from app.db.repositories import assessment_repo as repo
from app.graph import prompts
from app.graph.state import AssessmentGraphState
from app.schemas.assessment import AssessmentSummaryOutput, ClinicianReviewDecision
from app.services import assessment_audit as audit
from app.tools.assessment_tools import ASSESSMENT_TOOLS

logger = logging.getLogger(__name__)

MessageT = TypeVar("MessageT", bound=BaseMessage)

LLMFactory = Callable[[str | None, float | None], BaseChatModel]

MAX_REFLECTION_ATTEMPTS = 2
MAX_HISTORY_MESSAGES = 40
TOOLS_BY_NAME = {tool.name: tool for tool in ASSESSMENT_TOOLS}
_LEVEL_ORDER = {"critical": 0, "high": 1, "elevated": 2}

_PAUSE_REQUEST = re.compile(
    r"^\W*(stop|pause|save|quit|exit|later|bye)\W*$"
    r"|\b(save (it |this |my progress |my answers )?(for later|and (stop|exit|quit))|save my progress"
    r"|continue (this )?later|finish (this )?later|pause (the |this )?(assessment|screening|session|for now)"
    r"|(can|could) we (stop|pause)|let'?s (stop|pause)|stop for (now|today))\b",
    re.IGNORECASE,
)
_DIAGNOSTIC_LANGUAGE = re.compile(
    r"\b(you (have|suffer from|are suffering from)|disorder|(?<!non-)diagnos\w*|meets? (the )?criteria"
    r"|consistent with|indicative of|major depressi\w*|clinical(ly)? depress\w*|PTSD|bipolar|OCD|ADHD"
    r"|antidepressant\w*|SSRIs?|dosage"
    r"|(should|recommend\w*|advis\w*|suggest\w*)\b.{0,40}\b(therapy|medication|treatment|CBT|counsell?ing))\b",
    re.IGNORECASE,
)


def stamp(message: MessageT) -> MessageT:
    """Record when a message was created (shown in the chat UI). `response_metadata` is never
    sent back to the model provider."""
    message.response_metadata.setdefault("created_at", datetime.now(UTC).isoformat())
    return message


def default_llm_factory(provider: str | None, temperature: float | None) -> BaseChatModel:
    return get_llm(provider, temperature)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_id(config: RunnableConfig) -> str:
    """The checkpointer thread is the single source of truth for which session we touch."""
    thread_id = (config.get("configurable") or {}).get("thread_id")
    if not thread_id:
        raise ValueError("config['configurable']['thread_id'] is required")
    return str(thread_id)


def _last_human_text(state: AssessmentGraphState) -> str | None:
    messages = state.get("messages") or []
    if messages and isinstance(messages[-1], HumanMessage):
        return str(messages[-1].text)
    return None


def _pause_requested(state: AssessmentGraphState) -> bool:
    text = _last_human_text(state)
    return bool(text and _PAUSE_REQUEST.search(text))


def _merge_flags(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []
    for flag in (f for group in groups for f in group):
        key = (flag["code"], flag["evidence"])
        if key not in seen:
            seen.add(key)
            merged.append(flag)
    return sorted(merged, key=lambda f: _LEVEL_ORDER[f["level"]])


def sync_metrics(record: AssessmentRecord, message_flags: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute the audit from stored data, persist it, and return the state mirror.

    Message-level flags are merged in so they survive a tool-driven audit that only sees
    stored domain data.
    """
    data = repo.load_domain_data(record)
    missing = audit.missing_fields(data)
    inconsistencies = [i.model_dump(mode="json") for i in audit.find_inconsistencies(data)]
    flags = _merge_flags([f.model_dump(mode="json") for f in audit.find_risk_flags(data)], message_flags)

    record.missing_fields = [m.model_dump(mode="json") for m in missing]
    record.inconsistencies = inconsistencies
    record.risk_flags = flags
    return {
        "completion_pct": audit.completion_percentage(data),
        "missing_fields": [f"{m.domain.value}.{m.field}" for m in missing],
        "inconsistencies": inconsistencies,
        "risk_flags": flags,
        "requires_urgent_escalation": any(f["requires_immediate_escalation"] for f in flags),
        "assessment_complete": not missing,
    }


def _early_submission(state: AssessmentGraphState) -> bool:
    return bool(state.get("finalize_requested")) and not state.get("assessment_complete")


def _audit_tags(state: AssessmentGraphState) -> dict[str, list[tuple[str, str]]]:
    return prompts.tag_audit_items(
        state.get("missing_fields") or [], state.get("inconsistencies") or [], state.get("risk_flags") or []
    )


def _deterministic_summary(
    record: AssessmentRecord, state: AssessmentGraphState, headline: str
) -> dict[str, Any]:
    """Rule-built summary used for escalations and when the LLM summary is unavailable."""
    data = repo.load_domain_data(record)
    tags = _audit_tags(state)
    flags = {tag: flag for (tag, _), flag in zip(tags["risks"], state.get("risk_flags") or [], strict=True)}
    review = [
        f"{tag} {'URGENT: ' if flag['level'] in ('critical', 'high') else ''}{flag['evidence']}"
        for tag, flag in flags.items()
    ]
    summary = AssessmentSummaryOutput(
        structured_assessment=data,
        reported_concerns_summary=headline,
        missing_or_inconsistent_info=[
            f"{tag} {text}" for tag, text in tags["missing"] + tags["inconsistencies"]
        ],
        areas_requiring_professional_review=review,
        completion_status=audit.completion_status(data, AssessmentStatus.AWAITING_CLINICIAN_REVIEW.value),
    )
    return summary.model_dump(mode="json")


def review_summary_rules(draft: dict[str, Any], tags: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Deterministic reflection checks. Returns a list of problems (empty = pass)."""
    issues: list[str] = []
    narrative = [draft["reported_concerns_summary"], *draft["missing_or_inconsistent_info"]]
    narrative += draft["areas_requiring_professional_review"]
    for text in narrative:
        if match := _DIAGNOSTIC_LANGUAGE.search(text):
            issues.append(f"Diagnostic or treatment language '{match.group(0)}' in: \"{text[:160]}\"")

    info = " ".join(draft["missing_or_inconsistent_info"])
    for tag, text in tags["missing"] + tags["inconsistencies"]:
        if tag not in info:
            issues.append(f"{tag} ({text}) is not listed in missing_or_inconsistent_info")

    review = draft["areas_requiring_professional_review"]
    for tag, text in tags["risks"]:
        if text.startswith(("CRITICAL", "HIGH")):
            entry = next((item for item in review if tag in item), None)
            if entry is None:
                issues.append(f"{tag} ({text}) is missing from areas_requiring_professional_review")
            elif "URGENT" not in entry.upper():
                issues.append(f"{tag} is critical/high but not marked URGENT")
    return issues


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


class AssessmentNodes:
    """Node implementations; the LLM factory is injectable so tests can script the model."""

    def __init__(self, llm_factory: LLMFactory = default_llm_factory) -> None:
        self._llm = llm_factory

    # -- context ------------------------------------------------------------

    def load_context(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Ensure the DB record exists, screen the new message, and mirror DB metrics into state."""
        session_id = _session_id(config)
        text = _last_human_text(state)
        new_flags = (
            [f.model_dump(mode="json") for f in audit.scan_text_for_risk(text, source="User said")]
            if text
            else []
        )
        message_flags = _merge_flags(state.get("message_risk_flags") or [], new_flags)

        with get_session() as db:
            record = repo.get_or_create(db, session_id, state.get("patient_alias"))
            if record.status == AssessmentStatus.REVIEWED or state.get("clinician_reviewed"):
                return {
                    "session_id": session_id,
                    "clinician_reviewed": True,
                    "messages": [stamp(AIMessage(prompts.SESSION_CLOSED_MESSAGE))],
                }
            if record.status == AssessmentStatus.INTERRUPTED:
                record.status = AssessmentStatus.IN_PROGRESS
            metrics = sync_metrics(record, message_flags)
            alias = record.patient_alias or "anonymous"

        defaults = {
            "draft_summary": None,
            "reflection_passed": False,
            "reflection_feedback": None,
            "reflection_attempts": 0,
            "clinician_reviewed": False,
            "clinician_notes": None,
            "final_output": None,
        }
        update = {k: v for k, v in defaults.items() if k not in state}
        if new_flags:
            logger.warning(
                "Risk language in user message (session=%s): %s", session_id, [f["code"] for f in new_flags]
            )
        return {
            **update,
            "session_id": session_id,
            "patient_alias": alias,
            "message_risk_flags": message_flags,
            **metrics,
        }

    # -- conversation ---------------------------------------------------------

    def interviewer(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        # Escalation and pause are handled deterministically; don't spend an LLM call.
        if state.get("requires_urgent_escalation") or _pause_requested(state):
            return {}
        llm = self._llm(state.get("llm_provider"), None).bind_tools(ASSESSMENT_TOOLS)
        history: list[AnyMessage] = trim_messages(
            state.get("messages") or [],
            strategy="last",
            token_counter=len,
            max_tokens=MAX_HISTORY_MESSAGES,
            start_on="human",
        )
        response = llm.invoke([SystemMessage(prompts.format_interviewer_prompt(state)), *history], config)
        return {"messages": [stamp(response)]}

    def tools(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Run requested tools with session_id injected from the thread, then refresh metrics."""
        session_id = _session_id(config)
        last = state["messages"][-1]
        results: list[ToolMessage] = []
        for call in getattr(last, "tool_calls", []):
            tool = TOOLS_BY_NAME.get(call["name"])
            if tool is None:
                output: Any = {
                    "ok": False,
                    "error": f"Unknown tool '{call['name']}'. Available: {list(TOOLS_BY_NAME)}",
                }
            else:
                # Drop any model-supplied session_id; only the thread's id is ever used.
                args = {k: v for k, v in (call.get("args") or {}).items() if k != "session_id"}
                if "session_id" in tool.args_schema.model_fields:  # type: ignore[union-attr]
                    args["session_id"] = session_id
                try:
                    output = tool.invoke(args)
                except Exception as exc:  # validation errors etc. go back to the model
                    output = {"ok": False, "error": str(exc)}
            results.append(
                stamp(
                    ToolMessage(
                        content=json.dumps(output, default=str),
                        tool_call_id=call.get("id") or "",
                        name=call["name"],
                    )
                )
            )

        with get_session() as db:
            record = repo.get_or_create(db, session_id)
            metrics = sync_metrics(record, state.get("message_risk_flags") or [])
        return {"messages": results, **metrics}

    def pause_session(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        with get_session() as db:
            repo.get_or_create(db, _session_id(config)).status = AssessmentStatus.INTERRUPTED
        return {"messages": [stamp(AIMessage(prompts.PAUSE_MESSAGE))]}

    def escalation_summary(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Crisis resources to the user now; an urgent, rule-built summary to the clinician queue."""
        with get_session() as db:
            record = repo.get_or_create(db, _session_id(config))
            summary = _deterministic_summary(
                record,
                state,
                "URGENT: screening paused after a safety-critical disclosure. The self-reported data "
                "collected so far and the triggering risk indicators are listed below for immediate review.",
            )
            record.clinical_summary = summary
            record.status = AssessmentStatus.AWAITING_CLINICIAN_REVIEW
        return {
            "messages": [stamp(AIMessage(prompts.ESCALATION_MESSAGE))],
            "draft_summary": summary,
            "reflection_passed": True,
            "reflection_feedback": None,
        }

    # -- summary & reflection -------------------------------------------------

    def generate_summary(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        with get_session() as db:
            record = repo.get_or_create(db, _session_id(config))
            data = repo.load_domain_data(record)
            try:
                llm = self._llm(state.get("llm_provider"), 0.0).with_structured_output(
                    prompts.SummaryNarrative
                )
                narrative = llm.invoke(
                    [
                        SystemMessage(prompts.SUMMARY_SYSTEM_PROMPT),
                        HumanMessage(
                            prompts.format_summary_request(
                                data.model_dump(mode="json", exclude_none=True),
                                _audit_tags(state),
                                state.get("reflection_feedback"),
                            )
                        ),
                    ],
                    config,
                )
                narrative = prompts.SummaryNarrative.model_validate(narrative)
            except Exception:
                logger.exception("Summary generation failed; using rule-built summary")
                return {
                    "draft_summary": _deterministic_summary(
                        record,
                        state,
                        "Automatic narrative summary unavailable; structured self-reports attached.",
                    )
                }

            summary = AssessmentSummaryOutput(
                structured_assessment=data,
                completion_status=audit.completion_status(
                    data, AssessmentStatus.AWAITING_CLINICIAN_REVIEW.value
                ),
                **narrative.model_dump(),
            )
        return {"draft_summary": summary.model_dump(mode="json")}

    def reflect_summary(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        draft = state["draft_summary"] or {}
        tags = _audit_tags(state)
        issues = review_summary_rules(draft, tags)
        feedback_parts: list[str] = []

        try:
            reviewer = self._llm(state.get("llm_provider"), 0.0).with_structured_output(
                prompts.ReflectionVerdict
            )
            verdict = prompts.ReflectionVerdict.model_validate(
                reviewer.invoke(
                    [
                        SystemMessage(prompts.REFLECTION_SYSTEM_PROMPT),
                        HumanMessage(
                            prompts.format_reflection_request(draft, draft["structured_assessment"], tags)
                        ),
                    ],
                    config,
                )
            )
            if not verdict.passed:
                issues += verdict.issues or ["LLM reviewer rejected the draft"]
                feedback_parts.append(verdict.feedback)
        except Exception:
            logger.exception("LLM reflection failed; relying on rule-based checks only")

        attempts = state.get("reflection_attempts", 0) + 1
        passed = not issues
        update: dict[str, Any] = {
            "reflection_passed": passed,
            "reflection_attempts": attempts,
            "reflection_feedback": None
            if passed
            else "\n".join([*(f"- {issue}" for issue in issues), *filter(None, feedback_parts)]),
        }
        if not passed:
            logger.warning("Summary reflection failed (attempt %s): %s", attempts, issues)
        if passed or attempts >= MAX_REFLECTION_ATTEMPTS:
            update["messages"] = [stamp(AIMessage(prompts.REVIEW_PENDING_MESSAGE))]
        return update

    # -- human in the loop ----------------------------------------------------

    def clinician_review_gate(self, state: AssessmentGraphState, config: RunnableConfig) -> dict[str, Any]:
        """Pause until a clinician resumes with `Command(resume={"approved": ..., "clinician_notes": ...})`.

        Everything before `interrupt()` re-runs on resume, so it must stay idempotent.
        """
        session_id = _session_id(config)
        draft = state.get("draft_summary")
        with get_session() as db:
            record = repo.get_or_create(db, session_id)
            record.clinical_summary = draft
            if record.status != AssessmentStatus.REVIEWED:
                record.status = AssessmentStatus.AWAITING_CLINICIAN_REVIEW

        raw = interrupt(
            {
                "type": "clinician_review",
                "session_id": session_id,
                "patient_alias": state.get("patient_alias"),
                "urgent": bool(state.get("requires_urgent_escalation")),
                "summary": draft,
                "risk_flags": state.get("risk_flags") or [],
                "reflection_passed": state.get("reflection_passed", False),
                "reflection_feedback": state.get("reflection_feedback"),
                "early_submission": _early_submission(state),
                "missing_fields": state.get("missing_fields") or [],
                "resume_with": {
                    "approved": "bool",
                    "clinician_notes": "str | null",
                    "revised_summary": "AssessmentSummaryOutput | null",
                },
            }
        )
        decision = ClinicianReviewDecision.model_validate(raw)
        reviewed_at = datetime.now(UTC).isoformat()
        # A clinician edit replaces the AI draft; the disclaimer is re-enforced by the schema.
        final_summary = (
            decision.revised_summary.model_dump(mode="json") if decision.revised_summary else draft
        )

        with get_session() as db:
            record = repo.get_or_create(db, session_id)
            record.clinical_summary = final_summary
            record.clinician_approved = decision.approved
            record.clinician_notes = decision.clinician_notes
            record.status = AssessmentStatus.REVIEWED

        return {
            "clinician_reviewed": True,
            "clinician_notes": decision.clinician_notes,
            "final_output": {
                "session_id": session_id,
                "summary": final_summary,
                "ai_draft_summary": draft,
                "summary_revised_by_clinician": decision.revised_summary is not None,
                "urgent": bool(state.get("requires_urgent_escalation")),
                "early_submission": _early_submission(state),
                "clinician_approved": decision.approved,
                "clinician_notes": decision.clinician_notes,
                "reviewed_at": reviewed_at,
            },
        }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def route_after_load(state: AssessmentGraphState) -> Literal["interviewer", "__end__"]:
    return END if state.get("clinician_reviewed") else "interviewer"


def route_after_interviewer(
    state: AssessmentGraphState,
) -> Literal["tools", "escalation_summary", "pause_session", "generate_summary", "__end__"]:
    last = (state.get("messages") or [None])[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    if state.get("requires_urgent_escalation"):
        return "escalation_summary"
    if _pause_requested(state):
        return "pause_session"
    if state.get("assessment_complete") or state.get("finalize_requested"):
        return "generate_summary"
    return END


def route_after_tools(state: AssessmentGraphState) -> Literal["escalation_summary", "interviewer"]:
    # A tool may have stored a safety-critical answer: escalate before the model speaks again.
    return "escalation_summary" if state.get("requires_urgent_escalation") else "interviewer"


def route_after_reflection(
    state: AssessmentGraphState,
) -> Literal["generate_summary", "clinician_review_gate"]:
    if not state.get("reflection_passed") and state.get("reflection_attempts", 0) < MAX_REFLECTION_ATTEMPTS:
        return "generate_summary"
    return "clinician_review_gate"
