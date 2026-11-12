"""End-to-end tests of the LangGraph screening workflow with a scripted chat model.

Everything is real except the LLM: SQLite assessment store, SqliteSaver checkpoints, the 4
tools, the audit engine, routing, reflection and the human-in-the-loop interrupt.

Run: `pytest tests/test_graph.py -v`. Live provider test: `RUN_LIVE_LLM_TESTS=1 pytest -m live`.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from app.core.exceptions import ConflictError
from app.db.checkpointer import create_checkpointer
from app.db.database import get_session
from app.db.repositories import assessment_repo as repo
from app.graph import nodes, prompts
from app.graph.workflow import build_graph, get_session_state, run_assessment_turn, submit_clinician_review
from app.tools.assessment_tools import store_assessment_response
from tests.profiles import CALM_PROFILE
from tests.scripted_model import CLEAN_SUMMARY, DIAGNOSTIC_SUMMARY, Scenario, ScriptedChatModel

SID = "graph-session-001"


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


@pytest.fixture
def model(scenario: Scenario) -> ScriptedChatModel:
    return ScriptedChatModel(responder=scenario)


@pytest.fixture
def providers() -> list[str | None]:
    return []


@pytest.fixture
def make_graph(
    temp_db: Path, tmp_path: Path, model: ScriptedChatModel, providers: list[str | None]
) -> Callable[[], CompiledStateGraph]:
    """Build a graph on a shared checkpoint file; call twice to simulate a server restart."""
    checkpoint_path = tmp_path / "langgraph_checkpoints.db"

    def factory(provider: str | None, temperature: float | None) -> ScriptedChatModel:
        providers.append(provider)
        return model

    return lambda: build_graph(factory, create_checkpointer(checkpoint_path))


@pytest.fixture
def graph(make_graph: Callable[[], CompiledStateGraph]) -> CompiledStateGraph:
    return make_graph()


def seed(session_id: str, skip: set[str] = frozenset()) -> None:  # type: ignore[assignment]
    for domain, data in CALM_PROFILE.items():
        if domain not in skip:
            store_assessment_response.invoke({"session_id": session_id, "domain": domain, "data": data})


def complete_assessment(
    graph: CompiledStateGraph, scenario: Scenario, session_id: str = SID
) -> dict[str, Any]:
    """Seed 5 domains, then let the interviewer store the last one in a real turn."""
    seed(session_id, skip={"concerns"})
    scenario.interviewer_plan[1] = [
        ("store_assessment_response", {"domain": "concerns", "data": CALM_PROFILE["concerns"]}),
        ("validate_and_audit_responses", {}),
    ]
    return run_assessment_turn(
        session_id, "Mostly exam stress; I'd like a better study balance.", graph=graph
    )


def db_record(session_id: str = SID) -> dict[str, Any]:
    with get_session() as db:
        record = repo.get_by_session_id(db, session_id)
        assert record is not None
        return {
            "status": record.status.value,
            "domain_data": record.domain_data,
            "risk_flags": record.risk_flags,
            "clinical_summary": record.clinical_summary,
            "clinician_notes": record.clinician_notes,
            "clinician_approved": record.clinician_approved,
            "patient_alias": record.patient_alias,
        }


# ---------------------------------------------------------------------------
# Multi-turn accumulation & checkpoint resumption
# ---------------------------------------------------------------------------


def test_multi_turn_state_accumulates_and_survives_restart(
    make_graph: Callable[[], CompiledStateGraph], scenario: Scenario, model: ScriptedChatModel,
    providers: list[str | None],
) -> None:  # fmt: skip
    scenario.interviewer_plan = {
        1: [("store_assessment_response", {"domain": "mood", "data": CALM_PROFILE["mood"]})],
        2: [
            ("store_assessment_response", {"domain": "stress", "data": CALM_PROFILE["stress"]}),
            ("validate_and_audit_responses", {}),
        ],
    }

    first = run_assessment_turn(SID, "Hi there", patient_alias="anon-42", graph=make_graph())
    assert first["reply"] == "Interviewer reply for turn 1"
    assert first["completion_pct"] == pytest.approx(22.2)
    assert first["status"] == "in_progress"

    restarted = make_graph()  # new graph + new SQLite connection, same checkpoint file
    second = run_assessment_turn(
        SID, "Stress is about 3/10, mostly exams", llm_provider="gemini", graph=restarted
    )
    assert second["completion_pct"] == pytest.approx(33.3)
    assert "stress.perceived_stress_level" not in second["missing_fields"]

    # The interviewer saw turn-1 history and the refreshed progress in its system prompt.
    last_interviewer_call = model.calls_for("interviewer")[-1]
    assert any(isinstance(m, HumanMessage) and m.content == "Hi there" for m in last_interviewer_call)
    assert "Completion: 22%" in str(model.calls_for("interviewer")[2][0].content)

    # Provider choice persists across turns until changed.
    run_assessment_turn(SID, "Thanks", graph=restarted)
    assert providers[-1] == "gemini"

    state = get_session_state(SID, graph=restarted)
    assert [m["content"] for m in state["messages"] if m["role"] == "user"] == [
        "Hi there",
        "Stress is about 3/10, mostly exams",
        "Thanks",
    ]
    assert state["patient_alias"] == "anon-42"
    assert {domain for domain, answers in db_record()["domain_data"].items() if answers} == {"mood", "stress"}


def test_session_id_is_injected_from_thread_not_model(graph: CompiledStateGraph, scenario: Scenario) -> None:
    scenario.interviewer_plan[1] = [
        ("store_assessment_response",
         {"session_id": "someone-elses-session", "domain": "sleep", "data": {"average_sleep_hours": 7}}),
    ]  # fmt: skip
    run_assessment_turn(SID, "I sleep about 7 hours", graph=graph)

    assert db_record()["domain_data"]["sleep"] == {"average_sleep_hours": 7.0}
    with get_session() as db:
        assert repo.get_by_session_id(db, "someone-elses-session") is None


def test_tool_errors_are_returned_to_the_model(graph: CompiledStateGraph, scenario: Scenario) -> None:
    scenario.interviewer_plan[1] = [("store_assessment_response", {"domain": "diet", "data": {"meals": 2}})]
    run_assessment_turn(SID, "I eat twice a day", graph=graph)

    tool_messages = [m for m in graph.get_state({"configurable": {"thread_id": SID}}).values["messages"]
                     if isinstance(m, ToolMessage)]  # fmt: skip
    assert '"ok": false' in tool_messages[0].content and "Unknown domain" in tool_messages[0].content


# ---------------------------------------------------------------------------
# Escalation routing
# ---------------------------------------------------------------------------


def test_disclosure_in_user_message_escalates_without_calling_the_llm(
    graph: CompiledStateGraph, model: ScriptedChatModel
) -> None:
    result = run_assessment_turn(SID, "Honestly I keep thinking about suicide lately.", graph=graph)

    assert result["replies"] == [prompts.ESCALATION_MESSAGE]
    assert "988" in result["reply"]
    assert result["requires_urgent_escalation"] is True
    assert result["awaiting_clinician_review"] is True
    assert model.calls_for("interviewer") == []  # deterministic path, no model involved

    record = db_record()
    assert record["status"] == "awaiting_clinician_review"
    flag = next(f for f in record["risk_flags"] if f["code"] == "self_harm_language")
    assert flag["evidence"].startswith("User said")

    pending = get_session_state(SID, graph=graph)["pending_review"]
    assert pending["urgent"] is True
    assert pending["summary"]["areas_requiring_professional_review"][0].startswith("[R1] URGENT")


def test_stored_self_harm_answer_escalates_after_tools(
    graph: CompiledStateGraph, scenario: Scenario, model: ScriptedChatModel
) -> None:
    scenario.interviewer_plan[1] = [
        ("store_assessment_response", {"domain": "mood", "data": {"self_harm_thoughts": True}}),
    ]
    result = run_assessment_turn(SID, "Yes, I have had those thoughts.", graph=graph)

    assert result["replies"] == [prompts.ESCALATION_MESSAGE]
    assert len(model.calls_for("interviewer")) == 1  # never got to speak after the tool result
    assert "self_harm_thoughts" in {f["code"] for f in result["risk_flags"]}
    assert result["awaiting_clinician_review"] is True


# ---------------------------------------------------------------------------
# Reflection loop
# ---------------------------------------------------------------------------


def test_reflection_rejects_diagnostic_language_and_regenerates(
    graph: CompiledStateGraph, scenario: Scenario, model: ScriptedChatModel
) -> None:
    scenario.summaries = [DIAGNOSTIC_SUMMARY, CLEAN_SUMMARY]
    result = complete_assessment(graph, scenario)

    summary_calls = model.calls_for("summary")
    assert len(summary_calls) == 2
    retry_request = str(summary_calls[1][-1].content)
    assert "REJECTED" in retry_request and "Major Depressive Disorder" in retry_request

    state = get_session_state(SID, graph=graph)
    assert state["reflection_passed"] is True
    assert state["reflection_attempts"] == 2
    assert result["draft_summary"]["reported_concerns_summary"] == CLEAN_SUMMARY["reported_concerns_summary"]
    assert result["replies"][-1] == prompts.REVIEW_PENDING_MESSAGE
    assert result["awaiting_clinician_review"] is True


def test_reflection_gives_up_after_two_attempts_and_warns_clinician(
    graph: CompiledStateGraph, scenario: Scenario, model: ScriptedChatModel
) -> None:
    scenario.summaries = [DIAGNOSTIC_SUMMARY]
    result = complete_assessment(graph, scenario)

    assert len(model.calls_for("summary")) == nodes.MAX_REFLECTION_ATTEMPTS
    assert result["replies"].count(prompts.REVIEW_PENDING_MESSAGE) == 1
    pending = get_session_state(SID, graph=graph)["pending_review"]
    assert pending["reflection_passed"] is False
    assert "Diagnostic or treatment language" in pending["reflection_feedback"]


def test_llm_reviewer_feedback_is_fed_back_to_the_writer(
    graph: CompiledStateGraph, scenario: Scenario, model: ScriptedChatModel
) -> None:
    scenario.verdicts = [
        {
            "passed": False,
            "issues": ["Mentions a sleep problem not in the record"],
            "feedback": "Remove the sleep claim.",
        },
        {"passed": True},
    ]
    complete_assessment(graph, scenario)

    summary_calls = model.calls_for("summary")
    assert len(summary_calls) == 2
    assert "Remove the sleep claim." in str(summary_calls[1][-1].content)


def test_rule_checks_require_every_audit_item_and_urgent_risks() -> None:
    tags = prompts.tag_audit_items(
        ["sleep.sleep_quality"],
        [{"description": "Stress 0/10 but severe panic"}],
        [{"level": "critical", "code": "self_harm_language", "evidence": "x"}],
    )
    draft = {**CLEAN_SUMMARY, "missing_or_inconsistent_info": ["[M1] Sleep quality not given"]}
    issues = nodes.review_summary_rules(draft, tags)

    assert any("[I1]" in i for i in issues)
    assert any("[R1]" in i for i in issues)
    fixed = {
        **draft,
        "missing_or_inconsistent_info": ["[M1] Sleep quality not given", "[I1] Stress 0/10 vs severe panic"],
        "areas_requiring_professional_review": ["[R1] URGENT: self-harm language in narrative"],
    }
    assert nodes.review_summary_rules(fixed, tags) == []


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("You have Major Depressive Disorder.", True),
        ("Consistent with generalised anxiety.", True),
        ("We recommend starting therapy and medication.", True),
        ("Reports feeling down nearly every day (PHQ-2 style score 5/6).", False),
        ("This non-diagnostic summary lists self-reported sleep difficulties.", False),
        ("GAD-2 style score 4/6; reports frequent worry.", False),
    ],
)
def test_diagnostic_language_detector(text: str, flagged: bool) -> None:
    assert bool(nodes._DIAGNOSTIC_LANGUAGE.search(text)) is flagged


# ---------------------------------------------------------------------------
# Human in the loop
# ---------------------------------------------------------------------------


def test_clinician_gate_pauses_then_resumes_to_reviewed(
    graph: CompiledStateGraph, scenario: Scenario, model: ScriptedChatModel
) -> None:
    result = complete_assessment(graph, scenario)
    assert result["awaiting_clinician_review"] is True
    assert db_record()["status"] == "awaiting_clinician_review"
    pending = get_session_state(SID, graph=graph)["pending_review"]
    assert pending["type"] == "clinician_review" and pending["urgent"] is False
    assert pending["summary"]["non_diagnostic_disclaimer"].startswith("This is an initial screening")

    # The user can't push the conversation forward while the review is pending.
    calls_before = len(model.calls)
    blocked = run_assessment_turn(SID, "Hello? Anything else?", graph=graph)
    assert blocked["accepted"] is False and blocked["awaiting_clinician_review"] is True
    assert len(model.calls) == calls_before

    reviewed = submit_clinician_review(SID, approved=True, clinician_notes="Low risk; offer study-skills group.",
                                       graph=graph)  # fmt: skip
    assert reviewed["status"] == "reviewed"
    assert reviewed["pending_review"] is None
    assert reviewed["final_output"]["clinician_approved"] is True
    assert reviewed["final_output"]["summary"] == result["draft_summary"]

    record = db_record()
    assert record["clinician_approved"] is True
    assert record["clinician_notes"] == "Low risk; offer study-skills group."
    assert record["clinical_summary"] == result["draft_summary"]

    closed = run_assessment_turn(SID, "Can I add something?", graph=graph)
    assert closed["replies"] == [prompts.SESSION_CLOSED_MESSAGE]
    with pytest.raises(ConflictError):
        submit_clinician_review(SID, approved=True, graph=graph)


def test_clinician_can_review_urgent_escalation(graph: CompiledStateGraph) -> None:
    run_assessment_turn(SID, "I don't want to wake up anymore.", graph=graph)
    reviewed = submit_clinician_review(SID, approved=False, clinician_notes="Called client; safety plan made.",
                                       graph=graph)  # fmt: skip

    assert reviewed["final_output"]["urgent"] is True
    assert db_record()["status"] == "reviewed"
    assert db_record()["clinician_approved"] is False


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


def test_pause_marks_interrupted_and_next_turn_resumes(
    graph: CompiledStateGraph, model: ScriptedChatModel
) -> None:
    run_assessment_turn(SID, "Hi", graph=graph)
    paused = run_assessment_turn(SID, "Can we pause and continue later?", graph=graph)

    assert paused["replies"] == [prompts.PAUSE_MESSAGE]
    assert paused["status"] == "interrupted"
    assert len(model.calls_for("interviewer")) == 1

    resumed = run_assessment_turn(SID, "I'm back, let's go on.", graph=graph)
    assert resumed["status"] == "in_progress"
    assert len(model.calls_for("interviewer")) == 2


@pytest.mark.parametrize(
    ("text", "is_pause"),
    [
        ("stop", True),
        ("Save my progress please", True),
        ("Let's continue later", True),
        ("I can't stop worrying about work", False),
        ("Stress stops me sleeping", False),
    ],
)
def test_pause_detection(text: str, is_pause: bool) -> None:
    assert bool(nodes._PAUSE_REQUEST.search(text)) is is_pause


# ---------------------------------------------------------------------------
# Live provider (opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_LLM_TESTS") != "1", reason="set RUN_LIVE_LLM_TESTS=1")
def test_live_interview_turn_stores_answers(temp_db: Path, tmp_path: Path) -> None:
    graph = build_graph(checkpointer=create_checkpointer(tmp_path / "live_checkpoints.db"))
    first = run_assessment_turn("live-1", "Hi, I'd like to start the screening.", graph=graph)
    assert first["reply"].strip()

    run_assessment_turn(
        "live-1",
        "Over the last two weeks I've had little interest in things on several days, and felt down "
        "more than half the days. My mood is about 4 out of 10. No thoughts of hurting myself.",
        graph=graph,
    )
    mood = db_record("live-1")["domain_data"].get("mood", {})
    assert mood.get("phq_little_interest") == 1
    assert mood.get("phq_feeling_down") == 2
