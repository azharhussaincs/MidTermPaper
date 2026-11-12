"""The exam's 5 synthetic assessment scenarios, end-to-end through the real graph (scripted LLM).

The scenarios run once per module; each test then checks one requirement. The same runner
powers `python -m scripts.run_exam_scenarios` (report) and `--seed-ui`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.execution_logger import ExecutionLogger, set_execution_logger
from app.db.database import dispose_db, get_session, init_db
from app.db.repositories import assessment_repo as repo
from app.evaluation.report import render_report
from app.evaluation.runner import ExamRun, ScenarioOutcome, purge_sessions, run_exam, scripted_graph_factory
from app.evaluation.scenarios import EXAM_SCENARIOS
from app.graph import prompts

EXPECTED_OUTPUT_KEYS = {
    "structured_assessment",
    "reported_concerns_summary",
    "missing_or_inconsistent_info",
    "areas_requiring_professional_review",
    "completion_status",
}


@pytest.fixture(scope="module")
def exam(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[ExamRun, Path]]:
    work = tmp_path_factory.mktemp("exam")
    tracer = ExecutionLogger(work / "trace.jsonl", keep_runs=True)
    set_execution_logger(tracer)
    db, checkpoints = work / "exam.db", work / "checkpoints.db"
    init_db(db)
    try:
        run = run_exam(
            mode="scripted",
            graph_factory=scripted_graph_factory(checkpoints),
            db_path=db,
            checkpoint_path=checkpoints,
        )
        yield run, work
    finally:
        dispose_db()
        set_execution_logger(None)


def outcome(run: ExamRun, key: str) -> ScenarioOutcome:
    return next(o for o in run.outcomes if o.scenario.key == key)


def test_all_five_scenarios_pass_every_check(exam: tuple[ExamRun, Path]) -> None:
    run, _ = exam
    assert [o.scenario.number for o in run.outcomes] == [1, 2, 3, 4, 5]
    failures = [(o.scenario.title, c.name, c.detail) for o in run.outcomes for c in o.checks if not c.passed]
    failures += [("suite", c.name, c.detail) for c in run.suite_checks if not c.passed]
    assert failures == []


def test_every_scenario_produces_the_five_expected_outputs(exam: tuple[ExamRun, Path]) -> None:
    run, _ = exam
    for o in run.outcomes:
        assert EXPECTED_OUTPUT_KEYS <= set(o.outputs), o.scenario.title
        assert o.outputs["completion_status"]["status"] == o.final_state["status"]


def test_scenario_1_complete_assessment_is_reviewed(exam: tuple[ExamRun, Path]) -> None:
    o = outcome(exam[0], "complete")
    assert o.outputs["completion_status"]["percentage"] == 100.0
    assert o.final_state["status"] == "reviewed"
    assert o.final_state["final_output"]["clinician_approved"] is True
    assert o.outputs["missing_or_inconsistent_info"] == []
    assert o.final_state["risk_flags"] == []  # consistent case: denials are not flagged
    assert "reports reduced interest on several days" in o.outputs["reported_concerns_summary"]


def test_scenario_2_lists_every_missing_field(exam: tuple[ExamRun, Path]) -> None:
    o = outcome(exam[0], "missing")
    listed = o.outputs["missing_or_inconsistent_info"]
    assert o.outputs["completion_status"]["percentage"] == 50.0
    assert [e.split()[0] for e in listed] == [f"[M{i}]" for i in range(1, 10)]
    assert {e.split()[1].split(".")[0] for e in listed} == {"anxiety", "functioning", "concerns"}
    assert o.final_state["pending_review"]["early_submission"] is True


def test_scenario_3_surfaces_contradictions(exam: tuple[ExamRun, Path]) -> None:
    o = outcome(exam[0], "conflicting")
    contradictions = [e for e in o.outputs["missing_or_inconsistent_info"] if e.startswith("[I")]
    assert len(contradictions) == 3
    assert any("0/10" in e and "frequent panic attacks" in e for e in contradictions)
    assert o.final_state["requires_urgent_escalation"] is False


def test_scenario_4_escalates_before_the_llm(exam: tuple[ExamRun, Path]) -> None:
    run, _ = exam
    o = outcome(run, "distress")
    disclosure_run = [r for r in o.runs if r.label == "turn"][-1]
    assert disclosure_run.path == [
        "load_context",
        "interviewer",
        "escalation_summary",
        "INTERRUPT(clinician_review)",
    ]
    assert disclosure_run.node_events("interviewer")[0].data == {"no_op": True}
    assert o.turn_results[-1]["replies"] == [prompts.ESCALATION_MESSAGE]
    assert run.queue_order[0] == o.session_id


def test_scenario_5_state_survives_a_fresh_process_and_resumes(exam: tuple[ExamRun, Path]) -> None:
    o = outcome(exam[0], "interrupted")
    paused, fresh = o.snapshots["after_pause"], o.snapshots["fresh_process"]
    assert paused["status"] == fresh["status"] == "interrupted"
    assert fresh["pid"] != o.snapshots["runner_pid"]
    assert fresh["message_count"] == paused["message_count"]
    assert o.final_state["status"] == "in_progress"
    assert o.final_state["completion_pct"] == 50.0


def test_jsonl_trace_records_nodes_routes_and_interrupts(exam: tuple[ExamRun, Path]) -> None:
    _, work = exam
    events = [json.loads(line) for line in (work / "trace.jsonl").read_text().splitlines()]
    kinds = {e["kind"] for e in events}
    assert {"node", "route", "interrupt", "end", "note"} <= kinds
    assert {e["session_id"] for e in events} == {f"exam-s{s.number}-{s.key}" for s in EXAM_SCENARIOS}
    routers = {e["data"]["via"] for e in events if e["kind"] == "route"}
    assert {
        "route_after_load",
        "route_after_interviewer",
        "route_after_tools",
        "route_after_reflection",
    } <= routers


def test_markdown_report_contains_every_scenario_and_output(exam: tuple[ExamRun, Path]) -> None:
    report = render_report(exam[0], llm_label="scripted", trace_path="trace.jsonl")
    assert "34/34 checks passed" in report
    for scenario in EXAM_SCENARIOS:
        assert f"## Scenario {scenario.number} — {scenario.title}" in report
    for heading in (
        "1. Structured assessment information",
        "2. Summary of reported concerns",
        "3. Missing or inconsistent information",
        "4. Areas requiring professional review",
        "5. Assessment completion status",
    ):
        assert report.count(heading) == 5


def test_seed_ui_leaves_each_case_at_its_demo_stage_and_is_idempotent(tmp_path: Path) -> None:
    db, checkpoints = tmp_path / "seed.db", tmp_path / "seed_checkpoints.db"
    init_db(db)
    ids = [f"demo-s{s.number}-{s.key}" for s in EXAM_SCENARIOS]
    try:
        for _ in range(2):  # seeding twice replaces, never duplicates
            purge_sessions(ids, checkpoints)
            run_exam(
                mode="scripted",
                graph_factory=scripted_graph_factory(checkpoints),
                db_path=db,
                checkpoint_path=checkpoints,
                session_prefix="demo",
                resume_interrupted=False,
            )
        with get_session() as session:
            records, total = repo.list_records(session, limit=50)
            statuses = {r.session_id: r.status.value for r in records}
    finally:
        dispose_db()

    assert total == 5
    assert statuses == {
        "demo-s1-complete": "reviewed",
        "demo-s2-missing": "awaiting_clinician_review",
        "demo-s3-conflicting": "awaiting_clinician_review",
        "demo-s4-distress": "awaiting_clinician_review",
        "demo-s5-interrupted": "interrupted",
    }
