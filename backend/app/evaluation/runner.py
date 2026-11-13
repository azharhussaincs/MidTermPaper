"""Runs the exam scenarios end-to-end through the real LangGraph workflow and verifies them.

Everything is real except (in scripted mode) the language model: SQLite store, SqliteSaver
checkpoints, the 4 tools, the audit engine, routing, reflection and the clinician interrupt.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.core.config import BACKEND_DIR
from app.core.execution_logger import GraphRunTrace, get_execution_logger
from app.db.checkpointer import close_checkpointer, create_checkpointer
from app.db.database import get_session
from app.db.models import AssessmentStatus
from app.db.repositories import assessment_repo as repo
from app.evaluation.scenarios import EXAM_SCENARIOS, ExamScenario
from app.evaluation.scripted_model import ScenarioResponder, ScriptedChatModel
from app.graph import prompts
from app.graph.workflow import (
    build_graph,
    finalize_session,
    get_session_state,
    run_assessment_turn,
    start_session,
    submit_clinician_review,
)
from app.services.assessment_views import queue_priority, to_queue_item

logger = logging.getLogger(__name__)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScenarioOutcome:
    scenario: ExamScenario
    session_id: str
    mode: str
    final_state: dict[str, Any]
    outputs: dict[str, Any]
    turn_results: list[dict[str, Any]] = field(default_factory=list)
    snapshots: dict[str, Any] = field(default_factory=dict)
    runs: list[GraphRunTrace] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def transcript(self) -> list[tuple[str, str, str | None]]:
        return [
            (m["role"], m["content"], m.get("created_at"))
            for m in self.final_state["messages"]
            if m["role"] in ("user", "assistant") and m["content"].strip()
        ]


@dataclass
class ExamRun:
    mode: str
    outcomes: list[ScenarioOutcome]
    suite_checks: list[Check]
    queue_order: list[str]

    @property
    def passed(self) -> bool:
        return all(o.passed for o in self.outcomes) and all(c.passed for c in self.suite_checks)


# ---------------------------------------------------------------------------
# The 5 expected outputs
# ---------------------------------------------------------------------------


def expected_outputs(state: dict[str, Any]) -> dict[str, Any]:
    """The exam's 5 expected outputs, from the reviewed/pending summary or, if none yet, live state."""
    final = state.get("final_output") or {}
    pending = state.get("pending_review") or {}
    summary = (
        final.get("summary")
        or pending.get("summary")
        or state.get("clinical_summary")
        or state.get("draft_summary")
    )

    if summary:
        structured = {
            domain: {k: v for k, v in answers.items() if v is not None}
            for domain, answers in summary["structured_assessment"].items()
        }
        completion = dict(summary["completion_status"])
        completion["status"] = state["status"]  # the record moves on (e.g. to 'reviewed') after the summary
        return {
            "source": "AssessmentSummaryOutput",
            "structured_assessment": structured,
            "reported_concerns_summary": summary["reported_concerns_summary"],
            "missing_or_inconsistent_info": summary["missing_or_inconsistent_info"],
            "areas_requiring_professional_review": summary["areas_requiring_professional_review"],
            "completion_status": completion,
            "non_diagnostic_disclaimer": summary["non_diagnostic_disclaimer"],
        }

    domain_map = state["domain_completion_map"]
    return {
        "source": "live audit (no summary yet: session not submitted)",
        "structured_assessment": {d: a for d, a in state["domain_data"].items() if a},
        "reported_concerns_summary": None,
        "missing_or_inconsistent_info": [f"[M{i}] {f}" for i, f in enumerate(state["missing_fields"], 1)]
        + [f"[I{i}] {item['description']}" for i, item in enumerate(state["inconsistencies"], 1)],
        "areas_requiring_professional_review": [
            f"[R{i}] {flag['level'].upper()} - {flag['code']}: {flag['evidence']}"
            for i, flag in enumerate(state["risk_flags"], 1)
        ],
        "completion_status": {
            "percentage": state["completion_pct"],
            "completed_domains": [d for d, p in domain_map.items() if p["completed"]],
            "pending_domains": [d for d, p in domain_map.items() if not p["completed"]],
            "status": state["status"],
        },
        "non_diagnostic_disclaimer": None,
    }


def _tags(entries: list[str], kind: str) -> list[str]:
    return [e for e in entries if e.startswith(f"[{kind}")]


# ---------------------------------------------------------------------------
# Per-scenario verification
# ---------------------------------------------------------------------------


def _check(name: str, passed: bool, detail: Any = "") -> Check:
    return Check(name, bool(passed), str(detail))


def _run_for(outcome: ScenarioOutcome, label: str, index: int = -1) -> GraphRunTrace | None:
    runs = [r for r in outcome.runs if r.label == label]
    return runs[index] if runs else None


def _checks_complete(o: ScenarioOutcome) -> list[Check]:
    out, s = o.outputs, o.final_state
    review_run = _run_for(o, "turn")
    return [
        _check("All 18 required fields collected (100%)", out["completion_status"]["percentage"] == 100,
               f"{out['completion_status']['percentage']}%"),
        _check("No missing fields or contradictions listed", out["missing_or_inconsistent_info"] == [],
               out["missing_or_inconsistent_info"]),
        _check("Reflection passed", s["reflection_passed"] is True, f"attempts={s['reflection_attempts']}"),
        _check("Graph routed generate_summary -> reflect_summary -> clinician gate",
               review_run is not None and {"generate_summary", "reflect_summary"} <= set(review_run.path)
               and review_run.path[-1].startswith("INTERRUPT"), review_run.path if review_run else None),
        _check("Entered awaiting_clinician_review before sign-off",
               o.snapshots.get("before_review", {}).get("status") == "awaiting_clinician_review",
               o.snapshots.get("before_review", {}).get("status")),
        _check("Clinician HITL approval resumed the graph to 'reviewed'",
               s["status"] == "reviewed" and (s["final_output"] or {}).get("clinician_approved") is True, s["status"]),
        _check("No urgent escalation", s["requires_urgent_escalation"] is False),
        _check("Non-diagnostic disclaimer present", out["non_diagnostic_disclaimer"] is not None),
    ]  # fmt: skip


def _checks_missing(o: ScenarioOutcome) -> list[Check]:
    out, s = o.outputs, o.final_state
    missing = s["missing_fields"]
    listed = _tags(out["missing_or_inconsistent_info"], "M")
    omitted_domains = {"anxiety", "functioning", "concerns"}
    return [
        _check("Completion reflects partial answers (50%)", out["completion_status"]["percentage"] == 50.0,
               f"{out['completion_status']['percentage']}%"),
        _check("Pending domains are anxiety, functioning, concerns",
               set(out["completion_status"]["pending_domains"]) == omitted_domains,
               out["completion_status"]["pending_domains"]),
        _check("Every omitted required field listed as [M#]", len(listed) == len(missing) == 9,
               f"{len(listed)} listed / {len(missing)} missing"),
        _check("Each [M#] names the omitted field", all(any(f in e for e in listed) for f in missing)),
        _check("Early submission recorded and queued for review",
               s["finalize_requested"] and s["status"] == "awaiting_clinician_review", s["status"]),
    ]  # fmt: skip


def _checks_conflicting(o: ScenarioOutcome) -> list[Check]:
    out, s = o.outputs, o.final_state
    codes = {i["code"] for i in s["inconsistencies"]}
    listed = _tags(out["missing_or_inconsistent_info"], "I")
    expected = {"low_stress_vs_acute_symptoms", "positive_mood_vs_distress", "no_anxiety_vs_panic"}
    return [
        _check("Audit engine detected the contradictions", expected <= codes, sorted(codes)),
        _check("Every contradiction surfaced as [I#] in the summary", len(listed) == len(s["inconsistencies"]) >= 3,
               f"{len(listed)} [I#] entries"),
        _check("'0/10 stress' contradiction names panic attacks and 2h sleep",
               any("0/10" in e and "panic" in e and "2h sleep" in e for e in listed)),
        _check("Related high-risk indicators flagged for review",
               len(_tags(out["areas_requiring_professional_review"], "R")) >= 2, out["areas_requiring_professional_review"]),
        _check("Queued for clinician verification (not escalated)",
               s["status"] == "awaiting_clinician_review" and not s["requires_urgent_escalation"], s["status"]),
    ]  # fmt: skip


def _checks_distress(o: ScenarioOutcome) -> list[Check]:
    out, s = o.outputs, o.final_state
    disclosure = o.turn_results[-1]
    run = _run_for(o, "turn")
    interviewer = run.node_events("interviewer") if run else []
    review = out["areas_requiring_professional_review"]
    return [
        _check("Crisis detected before any LLM call (interviewer skipped)",
               bool(interviewer) and all(e.data.get("no_op") for e in interviewer), run.path if run else None),
        _check("Routed straight to escalation_summary -> clinician gate",
               run is not None and "escalation_summary" in run.path and run.path[-1].startswith("INTERRUPT"),
               run.path if run else None),
        _check("Crisis helpline resources delivered immediately",
               disclosure["replies"] == [prompts.ESCALATION_MESSAGE] and "988" in disclosure["reply"]),
        _check("requires_urgent_escalation = True", s["requires_urgent_escalation"] is True),
        _check("[R1] is URGENT", bool(review) and review[0].startswith("[R1] URGENT"), review[:1]),
        _check("Normal multi-turn completion bypassed", out["completion_status"]["percentage"] < 100,
               f"{out['completion_status']['percentage']}%"),
        _check("Status awaiting_clinician_review", s["status"] == "awaiting_clinician_review", s["status"]),
    ]  # fmt: skip


def _checks_interrupted(o: ScenarioOutcome) -> list[Check]:
    paused = o.snapshots.get("after_pause", {})
    fresh = o.snapshots.get("fresh_process")
    resumed = o.final_state
    pause_run = _run_for(o, "turn", index=len(o.scenario.turns) - 1)
    checks = [
        _check("Pause handled without an LLM call (pause_session node)",
               pause_run is not None and "pause_session" in pause_run.path, pause_run.path if pause_run else None),
        _check("Status became 'interrupted'", paused.get("status") == "interrupted", paused.get("status")),
        _check("2 domains saved before the pause", paused.get("completion_pct") == 33.3, paused.get("completion_pct")),
    ]  # fmt: skip
    if fresh is not None:
        checks += [
            _check("A separate OS process read the same checkpoint", fresh.get("pid") not in (None, o.snapshots.get("runner_pid")),
                   f"pid {fresh.get('pid')}"),
            _check("Fresh process sees identical state (messages, completion, status)",
                   fresh.get("message_count") == paused.get("message_count")
                   and fresh.get("completion_pct") == paused.get("completion_pct")
                   and fresh.get("status") == "interrupted", fresh),
        ]  # fmt: skip
    if o.scenario.resume_turns and "after_pause" in o.snapshots and resumed["status"] != "interrupted":
        users = [m["content"] for m in resumed["messages"] if m["role"] == "user"]
        checks += [
            _check("Resumed on the same session_id with full history",
                   users[: len(o.scenario.turns)] == [t.user for t in o.scenario.turns], f"{len(users)} user messages"),
            _check("Resume continued from the checkpoint (in_progress, 50%)",
                   resumed["status"] == "in_progress" and resumed["completion_pct"] == 50.0,
                   f"{resumed['status']} {resumed['completion_pct']}%"),
        ]  # fmt: skip
    return checks


CHECKS: dict[str, Callable[[ScenarioOutcome], list[Check]]] = {
    "complete": _checks_complete,
    "missing": _checks_missing,
    "conflicting": _checks_conflicting,
    "distress": _checks_distress,
    "interrupted": _checks_interrupted,
}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

GraphFactory = Callable[[ExamScenario], CompiledStateGraph]


def scripted_graph_factory(checkpoint_path: Path) -> GraphFactory:
    """One deterministic model per scenario; each graph gets its own checkpointer connection."""

    def factory(scenario: ExamScenario) -> CompiledStateGraph:
        model = ScriptedChatModel(responder=ScenarioResponder(scenario.all_turns))
        return build_graph(lambda provider, temperature: model, create_checkpointer(checkpoint_path))

    return factory


def live_graph_factory(checkpoint_path: Path) -> GraphFactory:
    return lambda scenario: build_graph(None, create_checkpointer(checkpoint_path))


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": state["status"],
        "completion_pct": state["completion_pct"],
        "message_count": len(state["messages"]),
        "missing_fields": len(state["missing_fields"]),
        "next_nodes": state["next_nodes"],
    }


def read_in_fresh_process(session_id: str, db_path: Path, checkpoint_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "app.evaluation.fresh_process", "--session-id", session_id,
         "--db", str(db_path), "--checkpoints", str(checkpoint_path)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120, check=True,
    )  # fmt: skip
    return json.loads(result.stdout.strip().splitlines()[-1])


def _close(graph: CompiledStateGraph) -> None:
    if graph.checkpointer is not None:
        close_checkpointer(graph.checkpointer)  # type: ignore[arg-type]


def run_scenario(
    scenario: ExamScenario,
    session_id: str,
    graph_factory: GraphFactory,
    *,
    mode: str,
    db_path: Path,
    checkpoint_path: Path,
    llm_provider: str | None = None,
    resume_interrupted: bool = True,
    clinician_signoff: bool = True,
) -> ScenarioOutcome:
    graph = graph_factory(scenario)
    turn_results: list[dict[str, Any]] = []
    snapshots: dict[str, Any] = {"runner_pid": os.getpid()}
    notes: list[str] = []
    try:
        start_session(session_id, scenario.alias, llm_provider, graph=graph)
        for turn in scenario.turns:
            turn_results.append(run_assessment_turn(session_id, turn.user, graph=graph))

        state = get_session_state(session_id, graph=graph)
        if scenario.finalize_early and state["pending_review"] is None:
            turn_results.append(finalize_session(session_id, graph=graph))
        elif mode == "live" and not scenario.resume_turns and state["pending_review"] is None:
            notes.append("Live model did not complete every field; submitted early to produce the summary.")
            turn_results.append(finalize_session(session_id, graph=graph))

        if scenario.resume_turns:
            state = get_session_state(session_id, graph=graph)
            snapshots["after_pause"] = _snapshot(state)
            if resume_interrupted:
                _close(graph)
                snapshots["fresh_process"] = read_in_fresh_process(session_id, db_path, checkpoint_path)
                graph = graph_factory(scenario)  # new graph + new SQLite connection: a "restarted" server
                for turn in scenario.resume_turns:
                    turn_results.append(run_assessment_turn(session_id, turn.user, graph=graph))

        state = get_session_state(session_id, graph=graph)
        if scenario.clinician_review and state["pending_review"] is not None:
            snapshots["before_review"] = _snapshot(state)
            if clinician_signoff:
                submit_clinician_review(session_id, graph=graph, **scenario.clinician_review)
        final_state = get_session_state(session_id, graph=graph)
    finally:
        _close(graph)

    outcome = ScenarioOutcome(
        scenario=scenario,
        session_id=session_id,
        mode=mode,
        final_state=final_state,
        outputs=expected_outputs(final_state),
        turn_results=turn_results,
        snapshots=snapshots,
        runs=list(get_execution_logger().runs_for(session_id)),
        notes=notes,
    )
    outcome.checks = CHECKS[scenario.key](outcome)
    return outcome


def clinician_queue_order() -> list[str]:
    with get_session() as db:
        awaiting, _ = repo.list_records(db, statuses=[AssessmentStatus.AWAITING_CLINICIAN_REVIEW], limit=1000)
        return [item.session_id for item in sorted((to_queue_item(r) for r in awaiting), key=queue_priority)]


def run_exam(
    *,
    mode: str,
    graph_factory: GraphFactory,
    db_path: Path,
    checkpoint_path: Path,
    session_prefix: str = "exam",
    scenarios: list[ExamScenario] | None = None,
    llm_provider: str | None = None,
    resume_interrupted: bool = True,
) -> ExamRun:
    """Run scenarios in order (the DB must already be initialised at `db_path`)."""
    outcomes = []
    for scenario in scenarios or EXAM_SCENARIOS:
        session_id = f"{session_prefix}-s{scenario.number}-{scenario.key}"
        logger.info("Running scenario %s (%s)", scenario.number, scenario.title)
        outcomes.append(
            run_scenario(
                scenario,
                session_id,
                graph_factory,
                mode=mode,
                db_path=db_path,
                checkpoint_path=checkpoint_path,
                llm_provider=llm_provider,
                resume_interrupted=resume_interrupted,
            )
        )

    order = clinician_queue_order()
    suite: list[Check] = []
    distress = next((o for o in outcomes if o.scenario.key == "distress"), None)
    if distress is not None:
        suite.append(_check("Urgent escalation (scenario 4) is first in the clinician queue",
                            bool(order) and order[0] == distress.session_id, order))  # fmt: skip
    suite.append(_check("Every scenario produced all 5 expected outputs", all(
        o.outputs["structured_assessment"] is not None and o.outputs["completion_status"] is not None
        and o.outputs["missing_or_inconsistent_info"] is not None and o.outputs["areas_requiring_professional_review"] is not None
        for o in outcomes)))  # fmt: skip
    return ExamRun(mode=mode, outcomes=outcomes, suite_checks=suite, queue_order=order)


def purge_sessions(session_ids: list[str], checkpoint_path: Path) -> int:
    """Delete assessment records and checkpoint threads (used to make --seed-ui idempotent)."""
    removed = 0
    with get_session() as db:
        for session_id in session_ids:
            record = repo.get_by_session_id(db, session_id)
            if record is not None:
                db.delete(record)
                removed += 1
    saver = create_checkpointer(checkpoint_path)
    try:
        for session_id in session_ids:
            saver.delete_thread(session_id)
    finally:
        close_checkpointer(saver)
    return removed
