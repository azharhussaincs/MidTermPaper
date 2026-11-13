"""Exercises the 4 assessment tools end to end against a temporary SQLite database.

Tools are called with `.invoke({...})`, exactly as LangGraph's ToolNode calls them.
Run: `pytest tests/test_tools.py -v` from the backend directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.db.database import get_engine, get_session, init_db
from app.db.models import AssessmentStatus
from app.db.repositories import assessment_repo as repo
from app.schemas.assessment import NON_DIAGNOSTIC_DISCLAIMER, AssessmentDomain, AssessmentSummaryOutput
from app.tools.assessment_tools import (
    ASSESSMENT_TOOLS,
    get_screening_questionnaire_guide,
    retrieve_assessment_record,
    store_assessment_response,
    validate_and_audit_responses,
)
from tests.profiles import CALM_PROFILE

pytestmark = pytest.mark.usefixtures("temp_db")

SID = "session-test-001"


def store(domain: str, data: dict[str, Any], session_id: str = SID) -> dict[str, Any]:
    return store_assessment_response.invoke({"session_id": session_id, "domain": domain, "data": data})


def audit(session_id: str = SID) -> dict[str, Any]:
    return validate_and_audit_responses.invoke({"session_id": session_id})


def codes(items: list[dict[str, Any]]) -> set[str]:
    return {item["code"] for item in items}


# ---------------------------------------------------------------------------
# 1. store_assessment_response
# ---------------------------------------------------------------------------


def test_store_creates_record_and_reports_completion() -> None:
    result = store("mood", CALM_PROFILE["mood"])

    assert result["ok"] is True
    assert result["domain_complete"] is True
    # 4 of 18 required fields answered
    assert result["completion_percentage"] == pytest.approx(22.2)
    assert "mood" not in result["pending_domains"]


def test_store_merges_partial_answers_across_turns() -> None:
    first = store("sleep", {"average_sleep_hours": 6})
    assert first["domain_complete"] is False
    assert set(first["missing_required_in_domain"]) == {"sleep_quality", "reports_sleep_problems"}

    second = store("sleep", {"sleep_quality": "fair", "reports_sleep_problems": True})
    assert second["domain_complete"] is True

    with get_session() as db:
        saved = repo.get_by_session_id(db, SID).domain_data["sleep"]
    assert saved == {"average_sleep_hours": 6.0, "sleep_quality": "fair", "reports_sleep_problems": True}


def test_store_accepts_domain_paraphrases() -> None:
    assert store("Sleep Patterns", {"average_sleep_hours": 7})["domain"] == "sleep"
    assert store("daily-activities", {"energy_level": 5})["domain"] == "functioning"


def test_store_returns_actionable_errors_instead_of_raising() -> None:
    bad_value = store("mood", {"phq_feeling_down": 7})
    assert bad_value["ok"] is False
    assert bad_value["errors"][0]["field"] == "phq_feeling_down"

    unknown_field = store("stress", {"stress_score": 5})
    assert unknown_field["ok"] is False
    assert "perceived_stress_level" in unknown_field["allowed_fields"]

    assert store("stress", {})["ok"] is False

    with pytest.raises(Exception, match="Unknown domain"):
        store("diet", {"meals": 2})


def test_store_resumes_interrupted_session() -> None:
    store("stress", {"perceived_stress_level": 4})
    with get_session() as db:
        repo.get_by_session_id(db, SID).status = AssessmentStatus.INTERRUPTED
    store("stress", {"stress_triggers": ["work"]})
    with get_session() as db:
        assert repo.get_by_session_id(db, SID).status is AssessmentStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# 2. retrieve_assessment_record
# ---------------------------------------------------------------------------


def test_retrieve_unknown_session() -> None:
    result = retrieve_assessment_record.invoke({"session_id": "nope"})
    assert result == {"ok": True, "found": False, "current": None, "history": []}


def test_retrieve_returns_current_and_history_for_alias() -> None:
    for sid in ("old-1", "old-2"):
        with get_session() as db:
            repo.get_or_create(db, sid, patient_alias="anon-42")
        store("stress", {"perceived_stress_level": 6, "stress_triggers": ["work"]}, session_id=sid)
    with get_session() as db:
        repo.get_or_create(db, "other-person", patient_alias="anon-7")

    store("mood", CALM_PROFILE["mood"])
    result = retrieve_assessment_record.invoke({"session_id": SID, "patient_alias": "anon-42"})

    assert result["found"] is True
    assert result["current"]["patient_alias"] == "anon-42"  # alias attached to current session
    assert result["current"]["domain_data"]["mood"]["overall_mood_rating"] == 8
    assert result["current"]["completion"]["completed_domains"] == ["mood"]
    assert {h["session_id"] for h in result["history"]} == {"old-1", "old-2"}


# ---------------------------------------------------------------------------
# 3. validate_and_audit_responses
# ---------------------------------------------------------------------------


def test_audit_requires_existing_session() -> None:
    assert audit("missing")["ok"] is False


def test_audit_lists_missing_fields_and_stays_in_progress() -> None:
    store("mood", CALM_PROFILE["mood"])
    report = audit()

    assert report["completion"]["status"] == "in_progress"
    missing = {(m["domain"], m["field"]) for m in report["missing_fields"]}
    assert ("sleep", "average_sleep_hours") in missing
    assert ("mood", "phq_feeling_down") not in missing
    assert all(m["prompt_hint"] for m in report["missing_fields"])


def test_audit_complete_calm_profile_has_no_flags_and_awaits_review() -> None:
    for domain, data in CALM_PROFILE.items():
        store(domain, data)
    report = audit()

    assert report["completion"]["percentage"] == 100.0
    assert report["missing_fields"] == []
    assert report["inconsistencies"] == []
    assert report["risk_flags"] == []
    assert report["requires_immediate_escalation"] is False
    with get_session() as db:
        record = repo.get_by_session_id(db, SID)
        assert record.status is AssessmentStatus.AWAITING_CLINICIAN_REVIEW


def test_audit_detects_low_stress_and_great_mood_vs_panic_and_no_sleep() -> None:
    """'0/10 stress and great mood' alongside 'severe panic attacks and 2 hours of sleep'."""
    store("stress", {"perceived_stress_level": 0, "stress_triggers": []})
    store("mood", {"overall_mood_rating": 9, "phq_little_interest": 0, "phq_feeling_down": 0})
    store("anxiety", {"panic_attacks": "severe", "gad_nervous_anxious": 0, "gad_uncontrollable_worry": 0})
    store("sleep", {"average_sleep_hours": 2})

    report = audit()
    found = codes(report["inconsistencies"])

    assert {"low_stress_vs_acute_symptoms", "positive_mood_vs_distress", "no_anxiety_vs_panic"} <= found
    low_stress = next(i for i in report["inconsistencies"] if i["code"] == "low_stress_vs_acute_symptoms")
    assert "severe panic attacks" in low_stress["description"] and "2h sleep" in low_stress["description"]
    assert {"severe_panic", "severe_sleep_deprivation"} <= codes(report["risk_flags"])


def test_audit_keeps_a_contradiction_when_the_rating_is_later_overwritten() -> None:
    """Live run, scenario 3: the model re-stored stress 0/10 as an inferred 10/10."""
    store("stress", {"perceived_stress_level": 0})
    store("anxiety", {"panic_attacks": "frequent"})
    store("sleep", {"average_sleep_hours": 2})
    store("stress", {"perceived_stress_level": 10, "stress_triggers": ["panic attacks"]})

    report = audit()
    found = {i["code"]: i for i in report["inconsistencies"]}

    assert "low_stress_vs_acute_symptoms" in found
    assert "Reported stress 0/10" in found["low_stress_vs_acute_symptoms"]["description"]
    changed = found["changed_perceived_stress_level"]
    assert changed["severity"] == "high"
    assert "0/10" in changed["description"] and "10/10" in changed["description"]


def test_restoring_the_original_answer_clears_the_revision_flag() -> None:
    store("stress", {"perceived_stress_level": 4})
    store("stress", {"perceived_stress_level": 7})
    store("stress", {"perceived_stress_level": 4, "stress_triggers": ["work"]})

    assert not any(i["code"].startswith("changed_") for i in audit()["inconsistencies"])


def test_free_text_and_list_updates_are_not_revisions() -> None:
    store("stress", {"stress_triggers": ["work"]})
    store("stress", {"stress_triggers": ["work", "money"]})
    store("mood", {"mood_description": "Tired"})
    store("mood", {"mood_description": "Tired but hopeful"})

    with get_session() as db:
        assert repo.get_by_session_id(db, SID).answer_revisions == []


def test_existing_database_gains_the_revisions_column(tmp_path: Path) -> None:
    db_path = tmp_path / "older.db"
    init_db(db_path)
    with get_engine().begin() as conn:
        conn.exec_driver_sql("ALTER TABLE assessment_records DROP COLUMN answer_revisions")

    init_db(db_path)
    with get_engine().connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(assessment_records)")}
    assert "answer_revisions" in columns
    assert store("stress", {"perceived_stress_level": 3})["ok"] is True


def test_audit_detects_no_sleep_issues_vs_waking_exhausted() -> None:
    store("sleep", {"reports_sleep_problems": False, "wakes_unrefreshed": True, "average_sleep_hours": 7})
    report = audit()

    item = next(i for i in report["inconsistencies"] if i["code"] == "no_sleep_issues_vs_symptoms")
    assert "waking up exhausted" in item["description"]


def test_audit_detects_hopelessness_rating_contradicted_by_narrative() -> None:
    store("mood", {"hopelessness_level": "none"})
    store("concerns", {"narrative": "Honestly it all feels hopeless lately."})
    assert "no_hopelessness_vs_narrative" in codes(audit()["inconsistencies"])


@pytest.mark.parametrize(
    "narrative",
    [
        "Some nights I think everyone would be better off dead without me.",
        "I have been self-harming again.",
        "I don't want to wake up anymore.",
        "I keep thinking about suicide.",
    ],
)
def test_audit_flags_self_harm_language_for_immediate_escalation(narrative: str) -> None:
    store("concerns", {"narrative": narrative})
    report = audit()

    flag = next(f for f in report["risk_flags"] if f["code"] == "self_harm_language")
    assert flag["level"] == "critical"
    assert flag["requires_immediate_escalation"] is True
    assert report["requires_immediate_escalation"] is True
    assert report["risk_flags"][0]["level"] == "critical"  # most severe first


def test_audit_flags_structured_distress_indicators() -> None:
    store(
        "mood",
        {
            "self_harm_thoughts": True,
            "hopelessness_level": "severe",
            "phq_little_interest": 3,
            "phq_feeling_down": 3,
        },
    )
    store("functioning", {"work_study_impact": "severe", "self_care": "significantly_neglected"})
    store("anxiety", {"gad_nervous_anxious": 2, "gad_uncontrollable_worry": 2})  # fmt: skip

    report = audit()
    flags = {f["code"]: f for f in report["risk_flags"]}

    assert flags["self_harm_thoughts"]["requires_immediate_escalation"] is True
    assert flags["severe_hopelessness"]["level"] == "high"
    assert flags["extreme_functional_impairment"]["requires_immediate_escalation"] is True
    assert "phq2_positive_screen" in flags and "gad2_positive_screen" in flags
    assert report["requires_professional_review"] is True

    with get_session() as db:  # flags are persisted on the record
        assert codes(repo.get_by_session_id(db, SID).risk_flags) == set(flags)


def test_audit_does_not_flag_neutral_text() -> None:
    store(
        "concerns", {"narrative": "Work is busy and I'd like better routines.", "support_goals": ["routine"]}
    )
    assert audit()["risk_flags"] == []


# ---------------------------------------------------------------------------
# 4. get_screening_questionnaire_guide
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", list(AssessmentDomain))
def test_guide_covers_every_required_field(domain: AssessmentDomain) -> None:
    from app.schemas.assessment import DOMAIN_MODELS, REQUIRED_FIELDS

    guide = get_screening_questionnaire_guide.invoke({"domain": domain.value})
    fields = {q["field"] for q in guide["questions"]}

    assert guide["ok"] is True and guide["domain"] == domain.value
    assert set(REQUIRED_FIELDS[domain]) <= fields
    assert fields <= set(DOMAIN_MODELS[domain].model_fields)  # guide only names storable fields
    assert any("diagnos" in rule for rule in guide["guardrails"])


def test_guide_mood_uses_phq2_frequency_scale_and_marks_safety_question() -> None:
    guide = get_screening_questionnaire_guide.invoke({"domain": "mood"})
    by_field = {q["field"]: q for q in guide["questions"]}

    assert by_field["phq_feeling_down"]["response_format"][3] == "Nearly every day"
    assert by_field["self_harm_thoughts"]["safety_critical"] is True


# ---------------------------------------------------------------------------
# Tool contracts & schemas
# ---------------------------------------------------------------------------


def test_tools_expose_tool_calling_schemas() -> None:
    names = {t.name for t in ASSESSMENT_TOOLS}
    assert names == {
        "store_assessment_response",
        "retrieve_assessment_record",
        "validate_and_audit_responses",
        "get_screening_questionnaire_guide",
    }
    for t in ASSESSMENT_TOOLS:
        spec = convert_to_openai_tool(t)["function"]
        assert len(spec["description"]) > 40
        # session_id is injected by the graph and must never be visible to the model
        assert "session_id" not in spec["parameters"].get("properties", {})

    domain_schema = convert_to_openai_tool(store_assessment_response)["function"]["parameters"]
    assert "concerns" in str(domain_schema)  # enum values are visible to the model


def test_tools_convert_to_gemini_function_declarations() -> None:
    from langchain_google_genai._function_utils import convert_to_genai_function_declarations

    (gemini_tool,) = convert_to_genai_function_declarations(ASSESSMENT_TOOLS)
    declarations = {d.name: d for d in gemini_tool.function_declarations}
    assert len(declarations) == 4
    domain = declarations["store_assessment_response"].parameters.properties["domain"]
    assert domain.enum == [d.value for d in AssessmentDomain]


def test_summary_output_always_carries_canonical_disclaimer() -> None:
    summary = AssessmentSummaryOutput.model_validate(
        {
            "structured_assessment": {},
            "reported_concerns_summary": "Reports exam-related stress.",
            "missing_or_inconsistent_info": [],
            "areas_requiring_professional_review": [],
            "completion_status": {"percentage": 100, "completed_domains": [], "pending_domains": [],
                                  "status": "awaiting_clinician_review"},
            "non_diagnostic_disclaimer": "You have anxiety disorder.",  # model tried to override
        }
    )  # fmt: skip
    assert summary.non_diagnostic_disclaimer == NON_DIAGNOSTIC_DISCLAIMER


# ---------------------------------------------------------------------------
# Optional: live Gemini tool call (runs only with a real GEMINI_API_KEY)
# ---------------------------------------------------------------------------


def _gemini_available() -> bool:
    from app.core.config import get_settings

    return get_settings().gemini_configured and os.getenv("RUN_LIVE_LLM_TESTS") == "1"


@pytest.mark.skipif(not _gemini_available(), reason="set RUN_LIVE_LLM_TESTS=1 and GEMINI_API_KEY")
def test_live_gemini_calls_store_tool() -> None:
    from app.core.llm_manager import get_llm

    llm = get_llm("gemini", temperature=0).bind_tools(ASSESSMENT_TOOLS)
    reply = llm.invoke(
        f"Session id is {SID}. The user said they sleep about 5 hours a night, sleep quality is poor, "
        "and yes they have sleep problems. Save this."
    )
    call = next(c for c in reply.tool_calls if c["name"] == "store_assessment_response")
    result = store_assessment_response.invoke(call["args"])
    assert result["ok"] is True, result
    assert result["domain"] == "sleep"


# ---------------------------------------------------------------------------
# Free-text crisis lexicon: denials vs disclosures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "escalates"),
    [
        ("No, I haven't had any thoughts of hurting myself.", False),
        ("No thoughts of self-harm.", False),
        ("I would never hurt myself.", False),
        ("I have no plans of suicide.", False),
        ("No panic attacks.", False),
        ("I don't want to wake up anymore.", True),
        ("I haven't stopped thinking about suicide.", True),
        ("I'm not sure, sometimes I think about suicide.", True),
        ("I would never hurt myself. But last night I cut myself.", True),
        ("Everything feels hopeless and I've been thinking about ending my life.", True),
        ("There is no reason to live.", True),
    ],
)
def test_explicit_denials_do_not_escalate_but_disclosures_always_do(text: str, escalates: bool) -> None:
    from app.services.assessment_audit import scan_text_for_risk

    flags = scan_text_for_risk(text)
    assert any(f.requires_immediate_escalation for f in flags) is escalates
    if text == "No panic attacks.":
        assert flags == []
