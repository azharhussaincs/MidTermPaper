"""Pydantic v2 schemas for the 6 screening domains, audit results and the final summary.

All domain fields are optional because answers arrive incrementally over a conversation;
which fields are *required for completion* is declared per domain in `REQUIRED_FIELDS`.
Unknown keys are rejected (`extra="forbid"`) so a tool call can't silently store junk.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

NON_DIAGNOSTIC_DISCLAIMER = (
    "This is an initial screening summary of self-reported information. It is not a "
    "diagnosis and does not recommend any treatment or medication. A qualified mental "
    "health professional must review it. If you are in immediate danger or thinking about "
    "harming yourself, contact local emergency services or a crisis line right away."
)

# 0 = not at all, 1 = several days, 2 = more than half the days, 3 = nearly every day
# (the 2-week frequency scale used by PHQ-2 / GAD-2).
FrequencyScore = Annotated[int, Field(ge=0, le=3)]
Severity = Literal["none", "mild", "moderate", "severe"]
ShortText = Annotated[str, Field(max_length=2000)]
TextList = Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=20)]


class AssessmentDomain(StrEnum):
    MOOD = "mood"
    STRESS = "stress"
    SLEEP = "sleep"
    ANXIETY = "anxiety"
    FUNCTIONING = "functioning"
    CONCERNS = "concerns"


DOMAIN_ALIASES: dict[str, AssessmentDomain] = {
    "mood_emotional_wellbeing": AssessmentDomain.MOOD,
    "emotional_wellbeing": AssessmentDomain.MOOD,
    "stress_levels": AssessmentDomain.STRESS,
    "sleep_patterns": AssessmentDomain.SLEEP,
    "anxiety_related_experiences": AssessmentDomain.ANXIETY,
    "daily_activities": AssessmentDomain.FUNCTIONING,
    "daily_functioning": AssessmentDomain.FUNCTIONING,
    "personal_concerns": AssessmentDomain.CONCERNS,
    "challenges": AssessmentDomain.CONCERNS,
}


def parse_domain(value: str | AssessmentDomain) -> AssessmentDomain:
    """Accept canonical names plus common LLM paraphrases ("Sleep Patterns", "daily-activities")."""
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_").replace("&", "")
    key = "_".join(filter(None, key.split("_")))
    try:
        return AssessmentDomain(key)
    except ValueError:
        if key in DOMAIN_ALIASES:
            return DOMAIN_ALIASES[key]
    valid = ", ".join(d.value for d in AssessmentDomain)
    raise ValueError(f"Unknown domain {value!r}; expected one of: {valid}")


# A free-text field records the person's own words. A bare option label ("More than half the days",
# "Yes", "7 out of 10") there is a reply to a different question, usually a one-tap answer to an open
# clarification: rejecting it makes the model ask again instead of filing it as a description.
_OPTION_ONLY = re.compile(
    r"^(not at all|several days|more than half (of )?the days|nearly every day|yes|no|sometimes|not sure|maybe"
    r"|\d+(\s*(out of|/)\s*10)?)[.!]?$",
    re.IGNORECASE,
)
OPTION_ONLY_ERROR = (
    "This is a one-tap option answer, not a description in the person's own words. Do not store it here: "
    "ask them to describe it in their own words, or store the option in the field it actually answers."
)
FREE_TEXT_FIELDS = ("mood_description", "notes", "narrative")


def option_only_fields(data: dict[str, Any]) -> list[str]:
    """Free-text fields in an incoming answer that hold only an option label (checked on store, not on load)."""
    return [
        f for f in FREE_TEXT_FIELDS if isinstance(data.get(f), str) and _OPTION_ONLY.match(data[f].strip())
    ]


# Items a patient rarely mentions unprompted, keyed to the words that show the topic was discussed.
# A value for one of these may only be stored once the patient has talked about the topic or was
# asked about it, so the agent cannot infer it from other answers (e.g. severe work impact →
# "self-care significantly neglected"), which would feed the risk rules with invented data.
_TOPIC_WORDS: dict[str, re.Pattern[str]] = {
    "energy_level": re.compile(
        r"energ|tired|exhaust|fatigu|drained|worn out|sluggish|lethargic", re.IGNORECASE
    ),
    "self_care": re.compile(
        r"self[- ]?care|look(ing)? after (my|your)self|take care of (my|your)self|hygiene|shower|wash|bath"
        r"|groom|dress|eat|meal|cook|clean|chores|brush",
        re.IGNORECASE,
    ),
}
UNGROUNDED_ERROR = (
    "The person has not talked about this and was not asked about it. Never infer it from other answers: "
    "store the other fields now and ask them about this item in your next question."
)


def ungrounded_fields(data: dict[str, Any], exchanges: list[tuple[str | None, str]]) -> list[str]:
    """Fields in an incoming answer whose topic appears in no (question, patient reply) pair so far."""
    return [
        field
        for field, words in _TOPIC_WORDS.items()
        if data.get(field) is not None
        and not any(
            words.search(answer) or (question and words.search(question)) for question, answer in exchanges
        )
    ]


class _DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MoodDomain(_DomainModel):
    """Mood & emotional wellbeing (PHQ-2 / WHO-5 style indicators)."""

    phq_little_interest: FrequencyScore | None = Field(
        None, description="Little interest or pleasure in doing things over the last 2 weeks (0-3)"
    )
    phq_feeling_down: FrequencyScore | None = Field(
        None, description="Feeling down, depressed or hopeless over the last 2 weeks (0-3)"
    )
    overall_mood_rating: int | None = Field(
        None, ge=1, le=10, description="Self-rated mood, 1=very low, 10=very good"
    )
    hopelessness_level: Severity | None = None
    self_harm_thoughts: bool | None = Field(
        None, description="Any thoughts of being better off dead or of hurting oneself"
    )
    who5_items: list[Annotated[int, Field(ge=0, le=5)]] | None = Field(
        None, min_length=5, max_length=5, description="WHO-5 wellbeing items, each 0-5"
    )
    mood_description: ShortText | None = None


class StressDomain(_DomainModel):
    """Perceived stress (0-10 accepted so "0/10" answers are representable) and triggers."""

    perceived_stress_level: int | None = Field(None, ge=0, le=10)
    stress_triggers: TextList | None = None
    stress_duration: Literal["days", "weeks", "months", "years"] | None = None
    feels_overwhelmed: bool | None = None
    coping_strategies: TextList | None = None
    notes: ShortText | None = None


class SleepDomain(_DomainModel):
    """Sleep duration, quality and insomnia/hypersomnia indicators."""

    average_sleep_hours: float | None = Field(None, ge=0, le=24)
    sleep_quality: Literal["very_poor", "poor", "fair", "good", "very_good"] | None = None
    reports_sleep_problems: bool | None = Field(
        None, description="The user's own view: do they have sleep problems?"
    )
    difficulty_falling_asleep: bool | None = None
    frequent_night_waking: bool | None = None
    early_morning_waking: bool | None = None
    wakes_unrefreshed: bool | None = None
    excessive_daytime_sleepiness: bool | None = None
    sleeping_more_than_usual: bool | None = None
    notes: ShortText | None = None


class AnxietyDomain(_DomainModel):
    """GAD-2 style indicators plus physical / cognitive symptoms."""

    gad_nervous_anxious: FrequencyScore | None = Field(
        None, description="Feeling nervous, anxious or on edge over the last 2 weeks (0-3)"
    )
    gad_uncontrollable_worry: FrequencyScore | None = Field(
        None, description="Not being able to stop or control worrying over the last 2 weeks (0-3)"
    )
    panic_attacks: Literal["none", "occasional", "frequent", "severe"] | None = None
    physical_symptoms: TextList | None = None
    cognitive_symptoms: TextList | None = None
    avoidance_behaviours: bool | None = None
    notes: ShortText | None = None


class FunctioningDomain(_DomainModel):
    """Daily activities: work/study, social engagement, energy and self-care."""

    work_study_impact: Severity | None = None
    social_engagement: Literal["normal", "reduced", "minimal", "isolated"] | None = None
    energy_level: int | None = Field(None, ge=1, le=10)
    self_care: Literal["maintained", "somewhat_neglected", "significantly_neglected"] | None = None
    days_missed_last_month: int | None = Field(None, ge=0, le=31)
    notes: ShortText | None = None


class ConcernsDomain(_DomainModel):
    """Open-ended narrative and what the person hopes to get from support."""

    narrative: Annotated[str, Field(max_length=5000)] | None = None
    main_challenges: TextList | None = None
    support_goals: TextList | None = None
    currently_receiving_support: bool | None = None


DOMAIN_MODELS: dict[AssessmentDomain, type[_DomainModel]] = {
    AssessmentDomain.MOOD: MoodDomain,
    AssessmentDomain.STRESS: StressDomain,
    AssessmentDomain.SLEEP: SleepDomain,
    AssessmentDomain.ANXIETY: AnxietyDomain,
    AssessmentDomain.FUNCTIONING: FunctioningDomain,
    AssessmentDomain.CONCERNS: ConcernsDomain,
}

REQUIRED_FIELDS: dict[AssessmentDomain, tuple[str, ...]] = {
    AssessmentDomain.MOOD: (
        "phq_little_interest",
        "phq_feeling_down",
        "overall_mood_rating",
        "self_harm_thoughts",
    ),
    AssessmentDomain.STRESS: ("perceived_stress_level", "stress_triggers"),
    AssessmentDomain.SLEEP: ("average_sleep_hours", "sleep_quality", "reports_sleep_problems"),
    AssessmentDomain.ANXIETY: ("gad_nervous_anxious", "gad_uncontrollable_worry", "panic_attacks"),
    AssessmentDomain.FUNCTIONING: ("work_study_impact", "social_engagement", "energy_level", "self_care"),
    AssessmentDomain.CONCERNS: ("narrative", "support_goals"),
}


class AssessmentDomainData(BaseModel):
    """All six domains as stored in `AssessmentRecord.domain_data`."""

    model_config = ConfigDict(extra="forbid")

    mood: MoodDomain = Field(default_factory=MoodDomain)
    stress: StressDomain = Field(default_factory=StressDomain)
    sleep: SleepDomain = Field(default_factory=SleepDomain)
    anxiety: AnxietyDomain = Field(default_factory=AnxietyDomain)
    functioning: FunctioningDomain = Field(default_factory=FunctioningDomain)
    concerns: ConcernsDomain = Field(default_factory=ConcernsDomain)

    def domain(self, domain: AssessmentDomain) -> _DomainModel:
        return getattr(self, domain.value)


# ---------------------------------------------------------------------------
# Audit results
# ---------------------------------------------------------------------------

RiskLevel = Literal["elevated", "high", "critical"]


class MissingField(BaseModel):
    domain: AssessmentDomain
    field: str
    prompt_hint: str


class Inconsistency(BaseModel):
    code: str
    domains: list[AssessmentDomain]
    description: str
    severity: Literal["low", "medium", "high"]


class RiskFlag(BaseModel):
    code: str
    level: RiskLevel
    domain: AssessmentDomain
    evidence: str
    requires_immediate_escalation: bool
    recommended_action: str


class CompletionStatus(BaseModel):
    percentage: float = Field(ge=0, le=100)
    completed_domains: list[AssessmentDomain]
    pending_domains: list[AssessmentDomain]
    status: Literal["in_progress", "awaiting_clinician_review", "reviewed", "interrupted"]


class AuditReport(BaseModel):
    session_id: str
    completion: CompletionStatus
    missing_fields: list[MissingField]
    inconsistencies: list[Inconsistency]
    risk_flags: list[RiskFlag]
    requires_immediate_escalation: bool
    requires_professional_review: bool


# ---------------------------------------------------------------------------
# Final summary (LLM structured output)
# ---------------------------------------------------------------------------


class AssessmentSummaryOutput(BaseModel):
    """Structured hand-off for a clinician. Organises self-reports; never diagnoses."""

    structured_assessment: AssessmentDomainData
    reported_concerns_summary: str = Field(
        description="Neutral summary of what the person reported, in their terms. No diagnoses."
    )
    missing_or_inconsistent_info: list[str]
    areas_requiring_professional_review: list[str]
    completion_status: CompletionStatus
    non_diagnostic_disclaimer: str = NON_DIAGNOSTIC_DISCLAIMER

    @field_validator("non_diagnostic_disclaimer", mode="before")
    @classmethod
    def _enforce_canonical_disclaimer(cls, _value: object) -> str:
        # Guardrail: whatever the model produced, the clinically reviewed wording wins.
        return NON_DIAGNOSTIC_DISCLAIMER


class ClinicianReviewDecision(BaseModel):
    """Payload a clinician submits to resume the human-in-the-loop gate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    approved: bool
    clinician_notes: str | None = Field(None, max_length=10_000)
    revised_summary: AssessmentSummaryOutput | None = None


# ---------------------------------------------------------------------------
# Records (API / tool output)
# ---------------------------------------------------------------------------


class AssessmentRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: str
    patient_alias: str | None
    status: str
    domain_data: dict[str, Any]
    missing_fields: list[dict[str, Any]]
    inconsistencies: list[dict[str, Any]]
    risk_flags: list[dict[str, Any]]
    clinical_summary: dict[str, Any] | None
    clinician_notes: str | None
    clinician_approved: bool
    created_at: datetime
    updated_at: datetime
