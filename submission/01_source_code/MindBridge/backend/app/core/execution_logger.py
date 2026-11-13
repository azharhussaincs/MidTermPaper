"""Structured execution trace of every LangGraph run (JSONL), plus LangSmith tracing setup.

Each graph run (a patient turn, an early finalisation, a clinician resume) is streamed with
`stream_mode="updates"`. For every node that executes we record what it did (messages,
tool calls/results, metric changes, reflection verdicts) and the routing decision that
followed. Events are appended to a JSONL file (one JSON object per line):

    {"ts": ..., "run_id": ..., "session_id": ..., "label": "turn", "step": 3,
     "kind": "node" | "route" | "interrupt" | "end" | "note", "node": ..., "data": {...}}

`scripts/run_exam_scenarios.py` keeps the runs in memory too and renders them as Markdown.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Which routing function decides the edge leaving each node (others have static edges).
ROUTERS = {
    "load_context": "route_after_load",
    "interviewer": "route_after_interviewer",
    "tools": "route_after_tools",
    "reflect_summary": "route_after_reflection",
}
_STATE_KEYS = (
    "completion_pct",
    "assessment_complete",
    "requires_urgent_escalation",
    "finalize_requested",
    "reflection_passed",
    "reflection_attempts",
    "clinician_reviewed",
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _preview(text: str, limit: int = 240) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_result(message: ToolMessage) -> dict[str, Any]:
    try:
        payload = json.loads(str(message.content))
    except (TypeError, ValueError):
        return {"tool": message.name, "raw": _preview(str(message.content), 120)}
    result: dict[str, Any] = {"tool": message.name, "ok": payload.get("ok")}
    for key in ("error", "domain", "stored_fields", "completion_percentage", "requires_immediate_escalation"):
        if key in payload:
            result[key] = payload[key]
    for key in ("missing_fields", "inconsistencies", "risk_flags"):
        if isinstance(payload.get(key), list):
            result[f"{key}_count"] = len(payload[key])
    if isinstance(payload.get("completion"), dict):
        result["completion_percentage"] = payload["completion"].get("percentage")
    return result


def summarise_update(update: dict[str, Any] | None) -> dict[str, Any]:
    """Compact, JSON-safe description of one node's state update."""
    if not update:
        return {"no_op": True}
    data: dict[str, Any] = {}
    for message in update.get("messages") or []:
        if isinstance(message, AIMessage) and message.tool_calls:
            data.setdefault("tool_calls", []).extend(
                {"name": call["name"], "args": call.get("args", {})} for call in message.tool_calls
            )
        elif isinstance(message, AIMessage) and str(message.text).strip():
            data["assistant"] = _preview(message.text)
        elif isinstance(message, ToolMessage):
            data.setdefault("tool_results", []).append(_tool_result(message))
        elif isinstance(message, HumanMessage):
            data["user"] = _preview(message.text)
    for key in _STATE_KEYS:
        if key in update:
            data[key] = update[key]
    if "missing_fields" in update:
        data["missing_count"] = len(update["missing_fields"] or [])
    if "inconsistencies" in update:
        data["inconsistencies"] = [item["code"] for item in update["inconsistencies"] or []]
    if "risk_flags" in update:
        data["risk_flags"] = [f"{flag['code']}:{flag['level']}" for flag in update["risk_flags"] or []]
    if update.get("reflection_feedback"):
        data["reflection_feedback"] = _preview(update["reflection_feedback"], 400)
    if update.get("draft_summary"):
        data["draft_summary"] = "generated"
    if update.get("final_output"):
        final = update["final_output"]
        data["final_output"] = {
            "clinician_approved": final.get("clinician_approved"),
            "summary_revised_by_clinician": final.get("summary_revised_by_clinician"),
        }
    return data


@dataclass(slots=True)
class TraceEvent:
    ts: str
    run_id: str
    session_id: str
    label: str
    step: int
    kind: str
    node: str | None
    data: dict[str, Any]


@dataclass
class GraphRunTrace:
    run_id: str
    session_id: str
    label: str
    started_at: str
    events: list[TraceEvent] = field(default_factory=list)
    finished_at: str | None = None

    @property
    def path(self) -> list[str]:
        """Executed nodes in order, ending with END or INTERRUPT."""
        nodes = [e.node for e in self.events if e.kind == "node" and e.node]
        last = next((e for e in reversed(self.events) if e.kind in ("end", "interrupt")), None)
        if last is not None:
            nodes.append("INTERRUPT(clinician_review)" if last.kind == "interrupt" else "END")
        return nodes

    def node_events(self, node: str) -> list[TraceEvent]:
        return [e for e in self.events if e.kind == "node" and e.node == node]


class ExecutionLogger:
    """Appends trace events to JSONL; optionally keeps runs in memory (for reports/tests)."""

    def __init__(self, jsonl_path: Path | None, *, keep_runs: bool = False) -> None:
        self.jsonl_path = jsonl_path
        self.keep_runs = keep_runs
        self.runs: list[GraphRunTrace] = []
        self._lock = threading.Lock()
        if jsonl_path is not None:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, run: GraphRunTrace, kind: str, node: str | None, data: dict[str, Any]) -> None:
        event = TraceEvent(_now(), run.run_id, run.session_id, run.label, len(run.events), kind, node, data)
        run.events.append(event)
        if self.jsonl_path is None:
            return
        line = json.dumps(asdict(event), default=str, ensure_ascii=False)
        with self._lock:
            try:
                with self.jsonl_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                logger.exception("Could not write execution trace to %s", self.jsonl_path)

    def start_run(self, session_id: str, label: str) -> GraphRunTrace:
        run = GraphRunTrace(uuid.uuid4().hex[:12], session_id, label, _now())
        if self.keep_runs:
            with self._lock:
                self.runs.append(run)
        return run

    def note(self, run: GraphRunTrace, message: str, **data: Any) -> None:
        self._emit(run, "note", None, {"message": message, **data})

    def record_chunk(self, run: GraphRunTrace, chunk: dict[str, Any]) -> None:
        for node, update in chunk.items():
            if node == "__interrupt__":
                payload = update[0].value if update else {}
                # The gate interrupts before emitting an update, so record the edge into it here.
                previous = next((e.node for e in reversed(run.events) if e.kind == "node"), None)
                if previous is not None:
                    self._emit(
                        run,
                        "route",
                        previous,
                        {"to": "clinician_review_gate", "via": ROUTERS.get(previous, "edge")},
                    )
                self._emit(
                    run,
                    "interrupt",
                    "clinician_review_gate",
                    {"type": payload.get("type"), "urgent": payload.get("urgent")},
                )
                continue
            previous = next((e.node for e in reversed(run.events) if e.kind == "node"), None)
            if previous is not None:
                self._emit(run, "route", previous, {"to": node, "via": ROUTERS.get(previous, "edge")})
            self._emit(run, "node", node, summarise_update(update if isinstance(update, dict) else None))

    def finish(self, run: GraphRunTrace, next_nodes: tuple[str, ...]) -> None:
        if not any(e.kind == "interrupt" for e in run.events):
            last = next((e.node for e in reversed(run.events) if e.kind == "node"), None)
            if last is not None:
                self._emit(run, "route", last, {"to": "END", "via": ROUTERS.get(last, "edge")})
            self._emit(run, "end", None, {"next": list(next_nodes)})
        run.finished_at = _now()

    def runs_for(self, session_id: str) -> Iterator[GraphRunTrace]:
        return (run for run in self.runs if run.session_id == session_id)


_logger: ExecutionLogger | None = None
_logger_lock = threading.Lock()


def get_execution_logger() -> ExecutionLogger:
    """Process-wide logger (JSONL at EXECUTION_LOG_PATH, or disabled)."""
    global _logger
    with _logger_lock:
        if _logger is None:
            settings = get_settings()
            _logger = ExecutionLogger(settings.execution_log_path if settings.execution_log_enabled else None)
        return _logger


def set_execution_logger(execution_logger: ExecutionLogger | None) -> None:
    global _logger
    with _logger_lock:
        _logger = execution_logger


def configure_langsmith(settings: Settings) -> bool:
    """LangChain reads tracing config from os.environ; pydantic-settings doesn't export it."""
    if settings.langchain_tracing_v2 and settings.langchain_api_key is not None:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key.get_secret_value()
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info("LangSmith tracing enabled (project=%s)", settings.langchain_project)
        return True
    if settings.langchain_tracing_v2:
        logger.warning("LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY is not set; tracing disabled")
    return False
