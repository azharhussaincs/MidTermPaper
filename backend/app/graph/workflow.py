"""StateGraph wiring, SQLite checkpointing, and the session-level API used by FastAPI.

    START -> load_context -+-> interviewer -+-> tools -+-> interviewer (loop)
                           |                |          +-> escalation_summary
                           +-> END (closed) +-> escalation_summary -> clinician_review_gate -> END
                                            +-> pause_session -> END
                                            +-> generate_summary -> reflect_summary -+-> generate_summary (retry)
                                            |                                        +-> clinician_review_gate
                                            +-> END (wait for the user's next turn)

One LangGraph thread per screening session: thread_id == session_id == AssessmentRecord.session_id.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.core.exceptions import ConflictError, NotFoundError
from app.core.execution_logger import get_execution_logger
from app.db.checkpointer import create_checkpointer
from app.db.database import get_session
from app.db.repositories import assessment_repo as repo
from app.graph import nodes, prompts
from app.graph.state import AssessmentGraphState
from app.schemas.assessment import AssessmentSummaryOutput, ClinicianReviewDecision
from app.services import assessment_audit as audit

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 50

_graph: CompiledStateGraph | None = None
_graph_lock = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}


def build_graph(
    llm_factory: nodes.LLMFactory | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    n = nodes.AssessmentNodes(llm_factory or nodes.default_llm_factory)
    graph = StateGraph(AssessmentGraphState)

    graph.add_node("load_context", n.load_context)
    graph.add_node("interviewer", n.interviewer)
    graph.add_node("tools", n.tools)
    graph.add_node("pause_session", n.pause_session)
    graph.add_node("escalation_summary", n.escalation_summary)
    graph.add_node("generate_summary", n.generate_summary)
    graph.add_node("reflect_summary", n.reflect_summary)
    graph.add_node("clinician_review_gate", n.clinician_review_gate)

    graph.add_edge(START, "load_context")
    graph.add_conditional_edges("load_context", nodes.route_after_load)
    graph.add_conditional_edges("interviewer", nodes.route_after_interviewer)
    graph.add_conditional_edges("tools", nodes.route_after_tools)
    graph.add_edge("pause_session", END)
    graph.add_edge("escalation_summary", "clinician_review_gate")
    graph.add_edge("generate_summary", "reflect_summary")
    graph.add_conditional_edges("reflect_summary", nodes.route_after_reflection)
    graph.add_edge("clinician_review_gate", END)

    return graph.compile(checkpointer=checkpointer if checkpointer is not None else create_checkpointer())


def get_graph() -> CompiledStateGraph:
    """Process-wide graph: the one registered by the app lifespan, else a default build."""
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = build_graph()
        return _graph


def set_graph(graph: CompiledStateGraph | None) -> None:
    global _graph
    with _graph_lock:
        _graph = graph


# ---------------------------------------------------------------------------
# Session API
# ---------------------------------------------------------------------------


@contextmanager
def _session_lock(session_id: str) -> Iterator[None]:
    """Serialise graph runs per session so concurrent requests can't interleave checkpoints."""
    with _graph_lock:
        lock = _session_locks.setdefault(session_id, threading.Lock())
    with lock:
        yield


def _run_graph(
    graph: CompiledStateGraph,
    graph_input: Any,
    config: RunnableConfig,
    session_id: str,
    label: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    """Run the graph to its next stop, recording every node and routing decision."""
    tracer = get_execution_logger()
    run = tracer.start_run(session_id, label)
    if note:
        tracer.note(run, note)
    for chunk in graph.stream(graph_input, config, stream_mode="updates"):
        tracer.record_chunk(run, chunk)
    snapshot = graph.get_state(config)
    tracer.finish(run, snapshot.next)
    return snapshot.values


def _config(session_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": session_id}, "recursion_limit": RECURSION_LIMIT}


def _pending_review(graph: CompiledStateGraph, config: RunnableConfig) -> dict[str, Any] | None:
    snapshot = graph.get_state(config)
    return next((i.value for i in snapshot.interrupts), None)


def _assistant_replies(messages: list[AnyMessage]) -> list[str]:
    return [
        str(m.text) for m in messages if isinstance(m, AIMessage) and not m.tool_calls and str(m.text).strip()
    ]


def _serialise_message(message: AnyMessage) -> dict[str, Any]:
    role = {HumanMessage: "user", AIMessage: "assistant", ToolMessage: "tool"}.get(
        type(message), message.type
    )
    item: dict[str, Any] = {
        "id": message.id,
        "role": role,
        "content": str(message.text),
        "created_at": message.response_metadata.get("created_at"),
    }
    if isinstance(message, AIMessage) and message.tool_calls:
        item["tool_calls"] = [call["name"] for call in message.tool_calls]
    if isinstance(message, ToolMessage):
        item["name"] = message.name
    return item


def _record_view(session_id: str) -> dict[str, Any] | None:
    with get_session() as db:
        record = repo.get_by_session_id(db, session_id)
        if record is None:
            return None
        data = repo.load_domain_data(record)
        return {
            "status": record.status.value,
            "patient_alias": record.patient_alias,
            "domain_data": record.domain_data or {},
            "domain_completion_map": audit.domain_completion_map(data),
            "clinical_summary": record.clinical_summary,
            "clinician_approved": record.clinician_approved,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }


def _turn_result(
    graph: CompiledStateGraph, session_id: str, replies: list[str], *, accepted: bool = True
) -> dict[str, Any]:
    config = _config(session_id)
    values = graph.get_state(config).values
    pending = _pending_review(graph, config)
    record = _record_view(session_id) or {}
    return {
        "session_id": session_id,
        "accepted": accepted,
        "replies": replies,
        "reply": "\n\n".join(replies),
        "status": record.get("status"),
        "completion_pct": values.get("completion_pct", 0.0),
        "domain_completion_map": record.get("domain_completion_map", {}),
        "missing_fields": values.get("missing_fields", []),
        "inconsistencies": values.get("inconsistencies", []),
        "risk_flags": values.get("risk_flags", []),
        "requires_urgent_escalation": values.get("requires_urgent_escalation", False),
        "assessment_complete": values.get("assessment_complete", False),
        "awaiting_clinician_review": pending is not None,
        "draft_summary": values.get("draft_summary"),
        "final_output": values.get("final_output"),
    }


def start_session(
    session_id: str,
    patient_alias: str | None = None,
    llm_provider: str | None = None,
    *,
    graph: CompiledStateGraph | None = None,
) -> dict[str, Any]:
    """Create the DB record and seed the thread with a fixed greeting (no LLM call needed)."""
    graph = graph or get_graph()
    config = _config(session_id)
    with _session_lock(session_id):
        with get_session() as db:
            if repo.get_by_session_id(db, session_id) is not None:
                raise ConflictError(f"Session '{session_id}' already exists", code="session_exists")
            record = repo.get_or_create(db, session_id, patient_alias)
            alias = record.patient_alias or "anonymous"

        values: dict[str, Any] = {
            "messages": [nodes.stamp(AIMessage(prompts.GREETING_MESSAGE))],
            "session_id": session_id,
            "patient_alias": alias,
            "llm_provider": llm_provider,
        }
        # Recorded as the interviewer's output: routing sees a plain reply and stops, so the
        # next user message starts a normal turn.
        graph.update_state(config, values, as_node="interviewer")
        tracer = get_execution_logger()
        run = tracer.start_run(session_id, "start")
        tracer.note(
            run, "update_state(as_node=interviewer): seeded fixed greeting (no LLM call)", alias=alias
        )
        tracer.finish(run, graph.get_state(config).next)
    return get_session_state(session_id, graph=graph)


def run_assessment_turn(
    session_id: str,
    user_message: str,
    patient_alias: str | None = None,
    llm_provider: str | None = None,
    *,
    graph: CompiledStateGraph | None = None,
) -> dict[str, Any]:
    """Send one user message and run the graph until it needs the user (or a clinician) again.

    `llm_provider` switches the engine for this and later turns; None keeps the current one.
    While a clinician review is pending the message is not processed (`accepted=False`).
    """
    graph = graph or get_graph()
    config = _config(session_id)

    with _session_lock(session_id):
        if _pending_review(graph, config) is not None:
            return _turn_result(
                graph,
                session_id,
                ["Your screening is currently with a professional for review. You'll be able to continue "
                 "once they've looked at it. If you feel unsafe, please contact emergency services or a crisis line."],
                accepted=False,
            )  # fmt: skip

        before = len(graph.get_state(config).values.get("messages", []))
        payload: dict[str, Any] = {
            "messages": [nodes.stamp(HumanMessage(user_message))],
            "session_id": session_id,
        }
        if patient_alias:
            payload["patient_alias"] = patient_alias
        if llm_provider is not None:
            payload["llm_provider"] = llm_provider

        values = _run_graph(graph, payload, config, session_id, "turn")
        return _turn_result(graph, session_id, _assistant_replies(values["messages"][before:]))


def finalize_session(session_id: str, *, graph: CompiledStateGraph | None = None) -> dict[str, Any]:
    """Submit early: summarise whatever has been collected and send it to the review queue.

    Missing fields are logged here and, via the [M#] tags, listed in the summary itself.
    """
    graph = graph or get_graph()
    config = _config(session_id)

    with _session_lock(session_id):
        values = graph.get_state(config).values
        if not values:
            raise NotFoundError(f"Session '{session_id}' not found", code="session_not_found")
        if values.get("clinician_reviewed"):
            raise ConflictError("This assessment has already been reviewed", code="already_reviewed")
        if _pending_review(graph, config) is not None:
            raise ConflictError("This assessment is already awaiting clinician review", code="review_pending")

        with get_session() as db:
            record = repo.get_or_create(db, session_id)
            metrics = nodes.sync_metrics(record, values.get("message_risk_flags") or [])
        if metrics["missing_fields"]:
            logger.warning(
                "Early submission of session %s with %d missing required fields: %s",
                session_id,
                len(metrics["missing_fields"]),
                ", ".join(metrics["missing_fields"]),
            )

        before = len(values.get("messages", []))
        graph.update_state(config, {**metrics, "finalize_requested": True}, as_node="interviewer")
        note = f"update_state(as_node=interviewer, finalize_requested=True); missing={len(metrics['missing_fields'])}"
        values = _run_graph(graph, None, config, session_id, "finalize_early", note=note)
        return _turn_result(graph, session_id, _assistant_replies(values["messages"][before:]))


def get_session_state(session_id: str, *, graph: CompiledStateGraph | None = None) -> dict[str, Any]:
    """Full snapshot for the UI / clinician dashboard."""
    graph = graph or get_graph()
    config = _config(session_id)
    snapshot = graph.get_state(config)
    values = snapshot.values
    record = _record_view(session_id) or {}
    return {
        **_turn_result(graph, session_id, []),
        "exists": bool(values) or bool(record),
        "patient_alias": values.get("patient_alias") or record.get("patient_alias"),
        "llm_provider": values.get("llm_provider"),
        "messages": [_serialise_message(m) for m in values.get("messages", [])],
        "domain_data": record.get("domain_data", {}),
        "clinical_summary": record.get("clinical_summary"),
        "next_nodes": list(snapshot.next),
        "pending_review": _pending_review(graph, config),
        "reflection_passed": values.get("reflection_passed"),
        "reflection_attempts": values.get("reflection_attempts", 0),
        "reflection_feedback": values.get("reflection_feedback"),
        "finalize_requested": values.get("finalize_requested", False),
        "clinician_reviewed": values.get("clinician_reviewed", False),
        "clinician_notes": values.get("clinician_notes"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def submit_clinician_review(
    session_id: str,
    approved: bool,
    clinician_notes: str | None = None,
    revised_summary: dict[str, Any] | AssessmentSummaryOutput | None = None,
    *,
    graph: CompiledStateGraph | None = None,
) -> dict[str, Any]:
    """Resume the human-in-the-loop gate. Raises ConflictError if no review is pending."""
    graph = graph or get_graph()
    config = _config(session_id)
    # Validate before resuming so a bad edit can't leave the thread half-resumed.
    decision = ClinicianReviewDecision.model_validate(
        {"approved": approved, "clinician_notes": clinician_notes, "revised_summary": revised_summary}
    )
    with _session_lock(session_id):
        if _pending_review(graph, config) is None:
            raise ConflictError(
                f"No clinician review is pending for session '{session_id}'", code="no_pending_review"
            )
        _run_graph(
            graph,
            Command(resume=decision.model_dump(mode="json")),
            config,
            session_id,
            "clinician_resume",
            note=f"Command(resume=approved={decision.approved}, revised={decision.revised_summary is not None})",
        )
    return get_session_state(session_id, graph=graph)


__all__ = [
    "build_graph",
    "finalize_session",
    "get_graph",
    "get_session_state",
    "run_assessment_turn",
    "set_graph",
    "start_session",
    "submit_clinician_review",
]
