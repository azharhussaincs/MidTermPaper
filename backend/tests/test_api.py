"""API integration tests: the real FastAPI app, SQLite, checkpointer and graph; scripted LLM.

Run: `pytest tests/test_api.py -v`
"""

from __future__ import annotations

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


def start(client: TestClient, alias: str = "anon-test", **body: Any) -> dict[str, Any]:
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
    calm = start(client, alias="anon-calm")["session_id"]
    crisis = start(client, alias="anon-crisis")["session_id"]
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
    a = start(client, alias="anon-a")["session_id"]
    scenario.interviewer_plan = {1: store_plan("mood")}
    say(client, a, "Mood is fine")
    client.post(f"/api/assessments/{a}/finalize")

    # C: early submission with an elevated risk (stress 9/10).
    c = start(client, alias="anon-c")["session_id"]
    scenario.interviewer_plan = {
        1: store_plan("stress", {"perceived_stress_level": 9, "stress_triggers": ["work"]})
    }
    say(client, c, "Stress is 9 out of 10, work is crushing me")
    client.post(f"/api/assessments/{c}/finalize")

    # B: urgent escalation, created last.
    b = start(client, alias="anon-b")["session_id"]
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
