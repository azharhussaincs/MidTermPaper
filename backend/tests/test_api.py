"""API integration tests: the real FastAPI app, SQLite, checkpointer and graph; scripted LLM.

Run: `pytest tests/test_api.py -v`
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.routes import system as system_routes
from app.core.config import get_settings
from app.core.llm_manager import LLMUnavailableError, reset_llm_configuration
from app.graph import prompts, workflow
from app.main import create_app
from app.schemas.assessment import NON_DIAGNOSTIC_DISCLAIMER
from tests.profiles import CALM_PROFILE
from tests.scripted_model import Scenario, ScriptedChatModel, echo_audit_summary


@pytest.fixture
def scenario() -> Scenario:
    s = Scenario()
    s.summaries = [echo_audit_summary]
    return s


@pytest.fixture
def model(scenario: Scenario) -> ScriptedChatModel:
    return ScriptedChatModel(responder=scenario)


@pytest.fixture
def client(tmp_path: Path, model: ScriptedChatModel) -> Iterator[TestClient]:
    app = create_app(
        llm_factory=lambda provider, temperature: model,
        db_path=tmp_path / "api.db",
        checkpoint_path=tmp_path / "api_checkpoints.db",
        warm_up_local=False,
    )
    with TestClient(app) as test_client:  # runs the lifespan
        yield test_client
    reset_llm_configuration()


def start(client: TestClient, alias: str | None = "anon-t01", **body: Any) -> dict[str, Any]:
    response = client.post("/api/assessments/start", json={"patient_alias": alias, **body})
    assert response.status_code == 201, response.text
    return response.json()


def say(client: TestClient, session_id: str, message: str, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/assessments/{session_id}/message", json={"message": message, **body})
    assert response.status_code == 200, response.text
    return response.json()


def store_plan(domain: str, data: dict[str, Any] | None = None) -> list[tuple[str, dict[str, Any]]]:
    return [("store_assessment_response", {"domain": domain, "data": data or CALM_PROFILE[domain]})]


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["message"]
    return error


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


def test_health_and_status(client: TestClient) -> None:
    assert client.get("/api/system/health").json() == {"status": "ok"}

    status = client.get("/api/system/status").json()
    assert status["status"] in ("ok", "degraded")
    assert set(status["llm"]) >= {
        "active_provider",
        "ollama_installed",
        "ollama_running",
        "local_model_available",
        "gemini_configured",
        "local_setup",
        "local_setup_error",
    }
    assert set(status["tracing"]) == {"requested", "enabled", "project"}


def test_runtime_provider_switching(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    warm_ups: list[dict[str, Any]] = []
    monkeypatch.setattr(system_routes, "warm_up_local_llm", lambda **kw: warm_ups.append(kw))

    switched = client.post("/api/system/llm/configure", json={"provider": "local", "local_model": "llama3.2"})
    assert switched.status_code == 200
    assert switched.json()["llm"]["configured_provider"] == "local"
    assert switched.json()["llm"]["local_model"] == "llama3.2"
    assert warm_ups == [{}]  # local setup kicked off in the background

    client.post("/api/system/llm/configure", json={"ensure_local": True})
    assert warm_ups[-1] == {"force": True}

    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    assert_error(
        client.post("/api/system/llm/configure", json={"provider": "gemini"}), 409, "gemini_not_configured"
    )

    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("test-key"))
    gemini = client.post("/api/system/llm/configure", json={"provider": "gemini"}).json()
    assert gemini["llm"]["configured_provider"] == "gemini"
    assert gemini["llm"]["active_provider"] == "gemini"

    error = assert_error(
        client.post("/api/system/llm/configure", json={"provider": "openai"}), 422, "validation_error"
    )
    assert error["details"][0]["field"] == "provider"


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------


def test_start_seeds_greeting_without_calling_the_llm(client: TestClient, model: ScriptedChatModel) -> None:
    session = start(client, alias="anon-42", llm_provider="gemini")

    assert session["session_id"].startswith("sess_")
    assert session["status"] == "in_progress"
    assert session["patient_alias"] == "anon-42"
    assert session["llm_provider"] == "gemini"
    assert session["completion_pct"] == 0
    assert [m["role"] for m in session["messages"]] == ["assistant"]
    assert session["messages"][0]["content"] == prompts.GREETING_MESSAGE
    assert model.calls == []

    generated = start(client, alias=None)  # type: ignore[arg-type]
    assert generated["patient_alias"].startswith("anon-")


def test_multi_turn_conversation_and_full_history(client: TestClient, scenario: Scenario) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood"), 2: store_plan("stress")}

    first = say(client, sid, "I've been okay, mood is decent")
    assert first["reply"] == "Interviewer reply for turn 1"
    assert first["completion_pct"] == pytest.approx(22.2)
    assert first["domain_completion_map"]["mood"] == {
        "completed": True,
        "answered": 4,
        "required": 4,
        "percentage": 100.0,
    }
    assert first["domain_completion_map"]["sleep"]["completed"] is False
    assert first["status"] == "in_progress" and first["requires_urgent_escalation"] is False

    second = say(client, sid, "Stress is about 3, mostly exams")
    assert second["completion_pct"] == pytest.approx(33.3)
    assert "stress.perceived_stress_level" not in second["missing_fields"]

    detail = client.get(f"/api/assessments/{sid}").json()
    assert [m["content"] for m in detail["messages"] if m["role"] == "user"] == [
        "I've been okay, mood is decent",
        "Stress is about 3, mostly exams",
    ]
    assert detail["messages"][0]["content"] == prompts.GREETING_MESSAGE
    assert any(m["role"] == "tool" and m["name"] == "store_assessment_response" for m in detail["messages"])
    assert detail["domain_data"]["mood"]["overall_mood_rating"] == 8
    assert detail["created_at"].endswith(("Z", "+00:00"))


def test_request_validation_and_unknown_session(client: TestClient) -> None:
    sid = start(client)["session_id"]
    assert_error(
        client.post(f"/api/assessments/{sid}/message", json={"message": "   "}), 422, "validation_error"
    )
    assert_error(client.post(f"/api/assessments/{sid}/message", json={"msg": "hi"}), 422, "validation_error")
    assert_error(
        client.post("/api/assessments/sess_nope/message", json={"message": "hi"}), 404, "session_not_found"
    )
    assert_error(client.get("/api/assessments/sess_nope"), 404, "session_not_found")
    assert_error(client.post("/api/assessments/sess_nope/finalize"), 404, "session_not_found")


def test_early_finalize_queues_partial_summary_with_every_missing_field(
    client: TestClient, scenario: Scenario, caplog: pytest.LogCaptureFixture
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood")}
    say(client, sid, "Mood is fine")

    with caplog.at_level(logging.WARNING, logger="app.graph.workflow"):
        result = client.post(f"/api/assessments/{sid}/finalize").json()

    assert result["status"] == "awaiting_clinician_review"
    assert result["awaiting_clinician_review"] is True
    assert result["replies"] == [prompts.REVIEW_PENDING_MESSAGE]
    assert len(result["missing_fields"]) == 14
    listed = result["draft_summary"]["missing_or_inconsistent_info"]
    assert len(listed) == 14 and all(entry.startswith("[M") for entry in listed)
    assert "Early submission" in caplog.text and "sleep.average_sleep_hours" in caplog.text

    detail = client.get(f"/api/assessments/{sid}").json()
    assert detail["pending_review"]["early_submission"] is True
    assert detail["reflection_passed"] is True

    assert_error(client.post(f"/api/assessments/{sid}/finalize"), 409, "review_pending")
    blocked = say(client, sid, "One more thing")
    assert blocked["accepted"] is False


def test_list_sessions_with_risk_and_status_filter(client: TestClient) -> None:
    calm = start(client, alias="anon-calm1")["session_id"]
    crisis = start(client, alias="anon-crisis1")["session_id"]
    escalated = say(client, crisis, "I have been thinking about suicide.")
    assert escalated["requires_urgent_escalation"] is True
    assert "988" in escalated["reply"]

    listing = client.get("/api/assessments").json()
    assert listing["total"] == 2
    by_id = {item["session_id"]: item for item in listing["items"]}
    assert by_id[crisis]["risk_level"] == "critical" and by_id[crisis]["urgent"] is True
    assert by_id[crisis]["status"] == "awaiting_clinician_review"
    assert by_id[calm]["risk_level"] == "none" and by_id[calm]["status"] == "in_progress"

    filtered = client.get("/api/assessments", params={"status": "in_progress"}).json()
    assert [item["session_id"] for item in filtered["items"]] == [calm]
    assert client.get("/api/assessments", params={"limit": 1}).json()["total"] == 2


# ---------------------------------------------------------------------------
# Clinician
# ---------------------------------------------------------------------------


def test_clinician_queue_priority_and_review_resumes_graph(client: TestClient, scenario: Scenario) -> None:
    # A: early submission, no risk. Created first, so it has waited longest.
    a = start(client, alias="anon-a1")["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood")}
    say(client, a, "Mood is fine")
    client.post(f"/api/assessments/{a}/finalize")

    # C: early submission with an elevated risk (stress 9/10).
    c = start(client, alias="anon-c1")["session_id"]
    scenario.interviewer_plan = {
        1: store_plan("stress", {"perceived_stress_level": 9, "stress_triggers": ["work"]})
    }
    say(client, c, "Stress is 9 out of 10, work is crushing me")
    client.post(f"/api/assessments/{c}/finalize")

    # B: urgent escalation, created last.
    b = start(client, alias="anon-b1")["session_id"]
    say(client, b, "I don't want to be alive anymore.")

    queue = client.get("/api/clinician/queue").json()
    assert [item["session_id"] for item in queue["awaiting_review"]] == [b, c, a]
    top = queue["awaiting_review"][0]
    assert top["urgent"] is True and top["risk_level"] == "critical" and top["early_submission"] is False
    assert queue["awaiting_review"][1]["early_submission"] is True
    assert queue["recently_reviewed"] == []

    # The clinician edits the AI draft; the disclaimer cannot be changed.
    pending = client.get(f"/api/assessments/{b}").json()["pending_review"]
    revised = {
        **pending["summary"],
        "reported_concerns_summary": "Disclosed thoughts of not wanting to be alive. Contacted same day.",
        "non_diagnostic_disclaimer": "edited",
    }
    response = client.post(
        f"/api/clinician/{b}/review",
        json={
            "approved": True,
            "clinician_notes": "Phoned client; safety plan agreed.",
            "revised_summary": revised,
        },
    )
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["status"] == "reviewed"
    assert review["clinician_approved"] is True and review["urgent"] is True
    assert review["summary_revised_by_clinician"] is True
    assert review["summary"]["reported_concerns_summary"].startswith("Disclosed thoughts")
    assert review["summary"]["non_diagnostic_disclaimer"] == NON_DIAGNOSTIC_DISCLAIMER
    assert review["ai_draft_summary"] == pending["summary"]

    detail = client.get(f"/api/assessments/{b}").json()
    assert detail["status"] == "reviewed"
    assert detail["clinician_notes"] == "Phoned client; safety plan agreed."
    assert detail["clinical_summary"]["reported_concerns_summary"].startswith("Disclosed thoughts")
    assert detail["pending_review"] is None

    queue = client.get("/api/clinician/queue").json()
    assert [item["session_id"] for item in queue["awaiting_review"]] == [c, a]
    assert [item["session_id"] for item in queue["recently_reviewed"]] == [b]
    assert queue["recently_reviewed"][0]["clinician_approved"] is True

    # Approving without edits keeps the AI draft.
    plain = client.post(
        f"/api/clinician/{a}/review", json={"approved": False, "clinician_notes": "Needs follow-up."}
    )
    assert plain.json()["summary_revised_by_clinician"] is False
    assert plain.json()["clinician_approved"] is False

    closed = say(client, b, "Hello again")
    assert closed["replies"] == [prompts.SESSION_CLOSED_MESSAGE]
    assert_error(
        client.post(f"/api/clinician/{b}/review", json={"approved": True, "clinician_notes": "again"}),
        409,
        "no_pending_review",
    )
    assert_error(
        client.post("/api/clinician/sess_nope/review", json={"approved": True, "clinician_notes": "x"}),
        404,
        "session_not_found",
    )
    assert_error(client.post(f"/api/clinician/{c}/review", json={"approved": True}), 422, "validation_error")


# ---------------------------------------------------------------------------
# Errors & CORS
# ---------------------------------------------------------------------------


def test_llm_outage_and_unexpected_errors_return_json_envelopes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = start(client)["session_id"]

    def llm_down(*args: Any, **kwargs: Any) -> Any:
        raise LLMUnavailableError("Local Ollama unavailable and GEMINI_API_KEY is not configured")

    monkeypatch.setattr(workflow, "run_assessment_turn", llm_down)
    error = assert_error(
        client.post(f"/api/assessments/{sid}/message", json={"message": "hi"}), 503, "llm_unavailable"
    )
    assert "GEMINI_API_KEY" in error["details"]

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(workflow, "run_assessment_turn", boom)
    unsafe_client = TestClient(client.app, raise_server_exceptions=False)
    response = unsafe_client.post(f"/api/assessments/{sid}/message", json={"message": "hi"})
    assert_error(response, 500, "internal_error")
    assert "secret internal detail" not in response.text and "Traceback" not in response.text


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_allows_vite_dev_server(client: TestClient, origin: str) -> None:
    response = client.options(
        "/api/assessments/start",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_errors_reach_the_browser_with_cors_headers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 500 built outside the CORS layer is blocked by the browser and looks like 'server unreachable'."""
    sid = start(client)["session_id"]
    origin = {"Origin": "http://localhost:5173"}

    retired = type(
        "GoogleModelNotFoundError", (Exception,), {"__module__": "langchain_google_genai.chat_models"}
    )

    def model_retired(*args: Any, **kwargs: Any) -> Any:
        raise retired("Error calling model 'gemini-2.5-flash' (NOT_FOUND): no longer available")

    monkeypatch.setattr(workflow, "run_assessment_turn", model_retired)
    response = client.post(f"/api/assessments/{sid}/message", json={"message": "hi"}, headers=origin)
    error = assert_error(response, 503, "llm_provider_error")
    assert "NOT_FOUND" in error["details"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    def crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(workflow, "run_assessment_turn", crash)
    response = client.post(f"/api/assessments/{sid}/message", json={"message": "hi"}, headers=origin)
    assert_error(response, 500, "internal_error")
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "secret internal detail" not in response.text


# ---------------------------------------------------------------------------
# Regressions from a real session: re-greeting, partial submission, pause, safety, real-name alias
# ---------------------------------------------------------------------------


def _assistant_texts(detail: dict[str, Any]) -> list[str]:
    return [m["content"] for m in detail["messages"] if m["role"] == "assistant" and m["content"].strip()]


@pytest.mark.parametrize("alias", ["Azhar", "Sam Lee", "ab", "anon test 1", "john.smith1"])
def test_start_rejects_real_name_aliases_with_an_explanation(client: TestClient, alias: str) -> None:
    error = assert_error(
        client.post("/api/assessments/start", json={"patient_alias": alias}), 422, "validation_error"
    )
    assert "anonymous code with at least one number" in error["details"][0]["message"]


def test_start_accepts_anonymous_codes_and_generates_one_when_blank(client: TestClient) -> None:
    assert start(client, alias="blue-28")["patient_alias"] == "blue-28"
    assert start(client, alias=None)["patient_alias"].startswith("anon-")


def test_greeting_is_sent_once_and_the_interviewer_never_regreets_or_sees_the_alias(
    client: TestClient, model: ScriptedChatModel
) -> None:
    sid = start(client, alias="anon-417")["session_id"]
    say(client, sid, "Up and down")
    say(client, sid, "Please pause here and save my progress so I can continue later.")
    say(client, sid, "I'm back")

    texts = _assistant_texts(client.get(f"/api/assessments/{sid}").json())
    assert texts.count(prompts.GREETING_MESSAGE) == 1
    assert all(a != b for a, b in zip(texts, texts[1:], strict=False)), (
        "an assistant message was repeated back to back"
    )
    for call in model.calls_for("interviewer"):
        system = str(call[0].content)
        assert "greeting has ALREADY been sent" in system
        assert "anon-417" not in system


def test_partial_submission_reports_one_consistent_progress(client: TestClient, scenario: Scenario) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood")}
    say(client, sid, "My mood answers")
    client.post(f"/api/assessments/{sid}/finalize")

    detail = client.get(f"/api/assessments/{sid}").json()
    completion = detail["pending_review"]["summary"]["completion_status"]
    assert detail["status"] == completion["status"] == "awaiting_clinician_review"
    assert detail["assessment_complete"] is False and detail["pending_review"]["early_submission"] is True
    assert completion["percentage"] == detail["completion_pct"] == pytest.approx(22.2)
    assert completion["completed_domains"] == ["mood"]
    assert [d for d, p in detail["domain_completion_map"].items() if p["completed"]] == ["mood"]
    assert detail["domain_data"]["mood"] == CALM_PROFILE["mood"]  # nothing the patient answered is dropped


def test_interrupted_assessment_keeps_answers_and_resumes_without_regreeting(
    client: TestClient, scenario: Scenario
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood")}
    say(client, sid, "My mood answers")
    paused = say(client, sid, "Can we stop here and continue later?")
    assert paused["status"] == "interrupted" and paused["replies"] == [prompts.PAUSE_MESSAGE]

    resumed = say(client, sid, "I'm back")
    detail = client.get(f"/api/assessments/{sid}").json()
    assert resumed["status"] == detail["status"] == "in_progress"
    assert detail["domain_data"]["mood"] == CALM_PROFILE["mood"]
    assert _assistant_texts(detail).count(prompts.GREETING_MESSAGE) == 1


def test_self_harm_answer_mid_checkin_escalates_without_a_normal_confirmation(
    client: TestClient, scenario: Scenario
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {
        1: store_plan("mood", {"phq_little_interest": 1, "phq_feeling_down": 2, "overall_mood_rating": 7}),
        2: store_plan("mood", {"self_harm_thoughts": True}),
    }
    say(client, sid, "Several days, more than half the days, 7 out of 10")
    result = say(client, sid, "Sometimes")

    assert result["replies"] == [prompts.ESCALATION_MESSAGE]
    assert result["requires_urgent_escalation"] is True and result["awaiting_clinician_review"] is True
    detail = client.get(f"/api/assessments/{sid}").json()
    assert prompts.REVIEW_PENDING_MESSAGE not in _assistant_texts(detail)
    assert detail["pending_review"]["urgent"] is True
    assert (
        detail["pending_review"]["early_submission"] is False
    )  # stopped for safety, not sent early by the patient
    assert detail["completion_pct"] == pytest.approx(22.2)

    queue = client.get("/api/clinician/queue").json()["awaiting_review"]
    assert queue[0]["session_id"] == sid and queue[0]["urgent"] is True

    blocked = say(client, sid, "Are you still there?")
    assert blocked["accepted"] is False and "crisis line" in blocked["reply"]


SELF_HARM_QUESTION = (
    "Sometimes when people go through difficult times, they might have thoughts of hurting themselves "
    "or feel that they'd be better off not being here. Have you had any thoughts like this?"
)


def test_ambiguous_answer_to_safety_question_escalates_even_if_the_model_stores_nothing(
    client: TestClient, scenario: Scenario, model: ScriptedChatModel
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_replies = {1: SELF_HARM_QUESTION}
    say(client, sid, "Mostly okay")

    result = say(client, sid, "Sometimes")  # no interviewer plan: the model would not store anything
    assert result["replies"] == [prompts.ESCALATION_MESSAGE]
    assert len(model.calls_for("interviewer")) == 1  # escalated before the model ran again
    flag = next(f for f in result["risk_flags"] if f["code"] == "self_harm_thoughts")
    assert flag["level"] == "critical" and '"Sometimes"' in flag["evidence"]

    queue = client.get("/api/clinician/queue").json()["awaiting_review"]
    assert queue[0]["session_id"] == sid and queue[0]["urgent"] is True


@pytest.mark.parametrize("reply", ["No", "No, never.", "No, I'm fine", "I haven't"])
def test_explicit_no_to_safety_question_continues_the_check_in(
    client: TestClient, scenario: Scenario, model: ScriptedChatModel, reply: str
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_replies = {1: SELF_HARM_QUESTION}
    say(client, sid, "Mostly okay")

    result = say(client, sid, reply)
    assert result["requires_urgent_escalation"] is False
    assert len(model.calls_for("interviewer")) == 2


def test_not_sure_to_safety_question_escalates(client: TestClient, scenario: Scenario) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_replies = {1: SELF_HARM_QUESTION}
    say(client, sid, "Mostly okay")
    result = say(client, sid, "Not sure")
    assert result["requires_urgent_escalation"] is True and result["replies"] == [prompts.ESCALATION_MESSAGE]


def test_declining_the_safety_question_continues_and_leaves_it_unanswered(
    client: TestClient, scenario: Scenario, model: ScriptedChatModel
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_replies = {1: SELF_HARM_QUESTION}
    say(client, sid, "Mostly okay")
    result = say(client, sid, "I'd rather not say")
    assert result["requires_urgent_escalation"] is False and len(model.calls_for("interviewer")) == 2
    assert "mood.self_harm_thoughts" in result["missing_fields"]  # listed for the clinician, not guessed


def test_escalated_check_in_is_stable_across_refresh_and_restart(
    client: TestClient, scenario: Scenario, model: ScriptedChatModel, tmp_path: Path
) -> None:
    """Partial answers, then "Sometimes": priority review, never complete or submitted early."""
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood", {"phq_little_interest": 1, "overall_mood_rating": 7})}
    scenario.interviewer_replies = {1: SELF_HARM_QUESTION}
    say(client, sid, "Several days, and about 7 out of 10")
    say(client, sid, "Sometimes")

    first = client.get(f"/api/assessments/{sid}").json()
    assert first == client.get(f"/api/assessments/{sid}").json()  # a refresh changes nothing
    assert first["status"] == "awaiting_clinician_review" and first["requires_urgent_escalation"] is True
    assert first["assessment_complete"] is False and first["finalize_requested"] is False
    assert first["pending_review"]["early_submission"] is False and first["completion_pct"] < 100
    assert first["domain_data"]["mood"] == {"phq_little_interest": 1, "overall_mood_rating": 7}

    # Restart: a new app on the same databases recovers the same state from the checkpoint.
    restarted = create_app(
        llm_factory=lambda provider, temperature: model,
        db_path=tmp_path / "api.db",
        checkpoint_path=tmp_path / "api_checkpoints.db",
        warm_up_local=False,
    )
    with TestClient(restarted) as again:
        recovered = again.get(f"/api/assessments/{sid}").json()
        assert (
            recovered["messages"] == first["messages"]
            and recovered["pending_review"] == first["pending_review"]
        )
        queue = again.get("/api/clinician/queue").json()["awaiting_review"]
        assert queue[0]["session_id"] == sid and queue[0]["urgent"] is True
        listed = next(i for i in again.get("/api/assessments").json()["items"] if i["session_id"] == sid)
        assert listed["urgent"] is True and listed["status"] == "awaiting_clinician_review"
        blocked = again.post(f"/api/assessments/{sid}/message", json={"message": "Hello?"}).json()
        assert blocked["accepted"] is False
        texts = _assistant_texts(again.get(f"/api/assessments/{sid}").json())
        assert texts.count(prompts.GREETING_MESSAGE) == 1 and texts.count(prompts.ESCALATION_MESSAGE) == 1


def test_retry_after_a_failed_model_turn_does_not_duplicate_messages(
    client: TestClient, scenario: Scenario, model: ScriptedChatModel
) -> None:
    sid = start(client)["session_id"]
    healthy = model.responder

    def fails_once(messages: Any) -> Any:
        object.__setattr__(model, "responder", healthy)
        raise RuntimeError("model timed out")

    object.__setattr__(model, "responder", fails_once)
    unsafe = TestClient(client.app, raise_server_exceptions=False)
    assert unsafe.post(f"/api/assessments/{sid}/message", json={"message": "Up and down"}).status_code == 500

    say(client, sid, "Up and down")  # the patient sends the same text again
    detail = client.get(f"/api/assessments/{sid}").json()
    users = [m["content"] for m in detail["messages"] if m["role"] == "user"]
    assert users == ["Up and down"]
    texts = _assistant_texts(detail)
    assert texts == [prompts.GREETING_MESSAGE, "Interviewer reply for turn 1"]

    say(client, sid, "Up and down")  # answered now: the same words again are a new message
    users = [
        m["content"] for m in client.get(f"/api/assessments/{sid}").json()["messages"] if m["role"] == "user"
    ]
    assert users == ["Up and down", "Up and down"]


CLARIFY_QUESTION = (
    "That's quite a high rating, though a moment ago you mentioned feeling low on more than half the days. "
    "Could you tell me a little more about how your mood has felt overall?"
)


def test_option_label_given_to_a_clarification_is_not_saved_as_a_description(
    client: TestClient, scenario: Scenario, model: ScriptedChatModel
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_replies = {1: CLARIFY_QUESTION}
    scenario.interviewer_plan = {2: store_plan("mood", {"mood_description": "More than half the days"})}
    say(client, sid, "Mostly okay")
    say(client, sid, "More than half the days")

    detail = client.get(f"/api/assessments/{sid}").json()
    assert "mood_description" not in detail["domain_data"].get("mood", {})
    stored = [
        m for m in detail["messages"] if m["role"] == "tool" and m["name"] == "store_assessment_response"
    ]
    result = json.loads(stored[-1]["content"])
    assert (
        result["ok"] is False and "own words" in result["errors"][0]["message"]
    )  # the model is told to ask again
    assert detail["messages"][-1]["role"] == "assistant"  # and the patient gets a reply, not a "saved" note
    users = [m["content"] for m in detail["messages"] if m["role"] == "user"]
    assert users[-1] == "More than half the days"  # the reply itself stays in the conversation


def test_progress_figures_share_one_source_after_a_safety_pause(
    client: TestClient, scenario: Scenario
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {
        1: store_plan("mood", {"phq_little_interest": 2, "phq_feeling_down": 2, "overall_mood_rating": 9})
    }
    scenario.interviewer_replies = {1: SELF_HARM_QUESTION}
    say(client, sid, "More than half the days, both, and 9 out of 10")
    say(client, sid, "Not sure")

    detail = client.get(f"/api/assessments/{sid}").json()
    progress = detail["domain_completion_map"]
    answered = sum(p["answered"] for p in progress.values())
    required = sum(p["required"] for p in progress.values())
    assert (answered, required) == (3, 18)
    assert detail["completion_pct"] == round(100 * answered / required, 1) == pytest.approx(16.7)
    assert [d for d, p in progress.items() if p["completed"]] == []  # the safety question is still unanswered
    assert progress["mood"]["answered"] == 3 and progress["mood"]["required"] == 4

    summary = detail["pending_review"]["summary"]["completion_status"]
    assert summary["percentage"] == detail["completion_pct"] and summary["completed_domains"] == []
    listed = next(i for i in client.get("/api/assessments").json()["items"] if i["session_id"] == sid)
    assert listed["completion_pct"] == detail["completion_pct"] and listed["urgent"] is True


def test_crisis_resources_lead_with_location_neutral_help() -> None:
    text = prompts.ESCALATION_MESSAGE
    assert text.index("local emergency number") < text.index("findahelpline.com") < text.index("988")
    assert "in the US" in text and "in the UK and Ireland" in text  # country numbers are labelled examples


def test_self_care_and_energy_the_patient_never_mentioned_are_not_stored(
    client: TestClient, scenario: Scenario
) -> None:
    """Live scenario 3 regression: severe work impact must not become an invented "self-care neglected"."""
    sid = start(client)["session_id"]
    scenario.interviewer_plan = {
        1: store_plan(
            "functioning",
            {"work_study_impact": "severe", "social_engagement": "isolated", "energy_level": 2,
             "self_care": "significantly_neglected"},
        )
    }  # fmt: skip
    say(client, sid, "I haven't been able to work at all this month and I barely see anyone.")

    detail = client.get(f"/api/assessments/{sid}").json()
    assert detail["domain_data"].get("functioning", {}) == {}  # nothing half-stored
    assert detail["requires_urgent_escalation"] is False
    result = json.loads(
        [m for m in detail["messages"] if m["role"] == "tool" and m["name"] == "store_assessment_response"][
            -1
        ]["content"]
    )
    assert result["ok"] is False
    assert {e["field"] for e in result["errors"]} == {"energy_level", "self_care"}


def test_self_care_and_energy_are_stored_once_the_patient_is_asked(
    client: TestClient, scenario: Scenario
) -> None:
    sid = start(client)["session_id"]
    scenario.interviewer_replies = {
        1: "How is your energy from 1 to 10, and how are you keeping up with eating and washing?"
    }
    scenario.interviewer_plan = {
        2: store_plan("functioning", {"energy_level": 3, "self_care": "somewhat_neglected"})
    }
    say(client, sid, "Work is hard at the moment.")
    say(client, sid, "About 3, and only just keeping up.")

    functioning = client.get(f"/api/assessments/{sid}").json()["domain_data"]["functioning"]
    assert functioning == {"energy_level": 3, "self_care": "somewhat_neglected"}
