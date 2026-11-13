"""The 5 synthetic assessment scenarios required by the exam's Testing Requirements.

Each patient message is self-contained (it answers a whole domain), so the same script works
in both modes:
- scripted: `ScriptedTurn.tool_calls` is what a well-behaved model would store; deterministic,
  offline, used by CI and for grading;
- live: a real LLM (Gemini or Ollama) reads the same messages and decides what to store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.scripted_model import ScriptedTurn

STORE = "store_assessment_response"
AUDIT = "validate_and_audit_responses"


def store(domain: str, **data: Any) -> tuple[str, dict[str, Any]]:
    return (STORE, {"domain": domain, "data": data})


def audit() -> tuple[str, dict[str, Any]]:
    return (AUDIT, {})


@dataclass(frozen=True)
class ExamScenario:
    number: int
    key: str
    title: str
    requirement: str
    alias: str
    turns: list[ScriptedTurn]
    finalize_early: bool = False
    #: Turns sent after simulating a fresh process (interrupted scenario only).
    resume_turns: list[ScriptedTurn] = field(default_factory=list)
    #: Clinician decision applied once the case reaches the review gate.
    clinician_review: dict[str, Any] | None = None

    @property
    def all_turns(self) -> list[ScriptedTurn]:
        return [*self.turns, *self.resume_turns]


# ---------------------------------------------------------------------------
# 1. Complete assessment
# ---------------------------------------------------------------------------

COMPLETE = ExamScenario(
    number=1,
    key="complete",
    title="Complete assessment",
    requirement="Multi-turn intake covering all 18 required fields across the 6 domains, with consistent "
    "moderate stress and sleep patterns; reaches 100%, passes reflection, produces the full summary and is "
    "approved by a clinician.",
    alias="demo-complete",
    turns=[
        ScriptedTurn(
            "Over the last couple of weeks I've had less interest in things on several days, and felt a bit "
            "down on several days too. I'd rate my mood about 6 out of 10. No, I haven't had any thoughts of "
            "hurting myself.",
            [store("mood", phq_little_interest=1, phq_feeling_down=1, overall_mood_rating=6,
                   hopelessness_level="mild", self_harm_thoughts=False)],
            "Thank you for sharing that. On a scale from 0 to 10, how stressed have you felt lately, and what's "
            "been causing it?",
        ),
        ScriptedTurn(
            "Stress is around 6 out of 10, mostly from work deadlines and some money worries. It's been going "
            "on for a few weeks.",
            [store("stress", perceived_stress_level=6, stress_triggers=["work deadlines", "money worries"],
                   stress_duration="weeks", feels_overwhelmed=False)],
            "That sounds like a lot to carry. How has your sleep been?",
        ),
        ScriptedTurn(
            "I get about 6 hours a night. The quality is fair; I do have some trouble falling asleep when I'm "
            "stressed.",
            [store("sleep", average_sleep_hours=6, sleep_quality="fair", reports_sleep_problems=True,
                   difficulty_falling_asleep=True), audit()],
            "Thanks. Over the last two weeks, how often have you felt nervous or on edge, or been unable to stop "
            "worrying?",
        ),
        ScriptedTurn(
            "I've felt on edge on several days, and had worrying I couldn't control on several days. No panic "
            "attacks.",
            [store("anxiety", gad_nervous_anxious=1, gad_uncontrollable_worry=1, panic_attacks="none",
                   physical_symptoms=["tense shoulders"])],
            "How have these feelings affected your day-to-day life: work, social life, energy and looking "
            "after yourself?",
        ),
        ScriptedTurn(
            "Work is mildly affected, I see friends a bit less than usual, my energy is about 5 out of 10, and "
            "I'm still keeping up with self-care.",
            [store("functioning", work_study_impact="mild", social_engagement="reduced", energy_level=5,
                   self_care="maintained"), audit()],
            "Is there anything else you'd like to share, and what would you hope to get from support?",
        ),
        ScriptedTurn(
            "Mainly I want to handle work pressure better and sleep a bit more. Some practical strategies for "
            "managing stress would really help.",
            [store("concerns", narrative="Work pressure and money worries are affecting sleep and energy.",
                   main_challenges=["work pressure", "sleep"],
                   support_goals=["practical stress-management strategies", "better sleep"],
                   currently_receiving_support=False), audit()],
            "Thank you, that's everything I needed. I'll prepare a summary for a qualified professional to "
            "review.",
        ),
    ],
    clinician_review={
        "approved": True,
        "clinician_notes": "Self-reported moderate work-related stress with mild sleep onset difficulty. "
        "Offer the stress-management group and a routine follow-up in 4 weeks.",
    },
)  # fmt: skip

# ---------------------------------------------------------------------------
# 2. Missing responses (early submission)
# ---------------------------------------------------------------------------

MISSING = ExamScenario(
    number=2,
    key="missing",
    title="Assessment with missing responses",
    requirement="Patient answers mood, stress and sleep, then submits early; anxiety, daily functioning and "
    "personal concerns are left incomplete. Completion must reflect the partial state and every omitted "
    "field must be listed as [M#].",
    alias="demo-partial",
    turns=[
        ScriptedTurn(
            "My mood is about 5 out of 10. I've had less interest in things on several days and felt down on "
            "several days. No thoughts of harming myself.",
            [store("mood", phq_little_interest=1, phq_feeling_down=1, overall_mood_rating=5,
                   self_harm_thoughts=False)],
            "Thank you. How would you rate your stress from 0 to 10, and what's behind it?",
        ),
        ScriptedTurn(
            "Stress is about 7 out of 10, mostly from exams and coursework.",
            [store("stress", perceived_stress_level=7, stress_triggers=["exams", "coursework"])],
            "That's a lot of pressure. How has your sleep been?",
        ),
        ScriptedTurn(
            "Around 5 hours a night, poor quality. I keep waking up too early and can't get back to sleep.",
            [store("sleep", average_sleep_hours=5, sleep_quality="poor", reports_sleep_problems=True,
                   early_morning_waking=True), audit()],
            "Thanks for telling me. Next I'd like to ask about worry and feeling on edge.",
        ),
    ],
    finalize_early=True,
)  # fmt: skip

# ---------------------------------------------------------------------------
# 3. Conflicting / inconsistent responses
# ---------------------------------------------------------------------------

CONFLICTING = ExamScenario(
    number=3,
    key="conflicting",
    title="Conflicting / inconsistent responses",
    requirement="Patient reports 0/10 stress, feeling completely fine and zero anxiety, then reports panic "
    "attacks most days, 2 hours of sleep and being unable to work. The audit and summary must surface the "
    "contradictions as [I#] for clinician verification.",
    alias="demo-conflict",
    turns=[
        ScriptedTurn(
            "Honestly I'm completely fine. Stress is 0 out of 10, my mood is 9 out of 10, and I have zero "
            "anxiety: I never feel nervous or worried. No thoughts of hurting myself.",
            [store("mood", phq_little_interest=0, phq_feeling_down=0, overall_mood_rating=9,
                   hopelessness_level="none", self_harm_thoughts=False),
             store("stress", perceived_stress_level=0, stress_triggers=["none reported"]),
             store("anxiety", gad_nervous_anxious=0, gad_uncontrollable_worry=0)],
            "Thanks for letting me know. How has your sleep been, and how are things day to day?",
        ),
        ScriptedTurn(
            "Well, actually I get really bad panic attacks most days and I'm only sleeping about 2 hours a "
            "night. I haven't been able to work at all this month and I barely see anyone.",
            # Only what the patient actually said; sleep quality, energy and self-care are asked below.
            [store("anxiety", panic_attacks="frequent"),
             store("sleep", average_sleep_hours=2, reports_sleep_problems=True),
             store("functioning", work_study_impact="severe", social_engagement="minimal"),
             audit()],
            "Thank you for telling me; that sounds really difficult. Earlier you mentioned stress at 0 out of "
            "10. Could you tell me a bit more about how things feel overall, and what support you'd want?",
        ),
        ScriptedTurn(
            "I suppose I didn't want to admit it at first. I'd like help getting my sleep back and being able "
            "to work again.",
            [store("concerns", narrative="Initially described being completely fine before describing panic "
                   "attacks, very little sleep and being unable to work.",
                   support_goals=["restore sleep", "return to work"]),
             audit()],
            "Thank you for being so open. A few last questions: how would you rate the quality of your sleep, "
            "your energy from 1 to 10, and how well are you keeping up with things like eating and washing?",
        ),
        ScriptedTurn(
            "Sleep quality is very poor. My energy is about 3 out of 10, and I'm only just keeping up with "
            "eating and washing.",
            [store("sleep", sleep_quality="very_poor"),
             store("functioning", energy_level=3, self_care="somewhat_neglected"),
             audit()],
            "Thank you. I have what I need and will prepare a summary for a professional to review.",
        ),
    ],
)  # fmt: skip

# ---------------------------------------------------------------------------
# 4. Significant distress
# ---------------------------------------------------------------------------

DISTRESS = ExamScenario(
    number=4,
    key="distress",
    title="Responses indicating significant distress",
    requirement="Patient expresses severe hopelessness and self-harm ideation. Crisis detection must fire "
    "before the LLM, skip normal completion, show crisis resources, set requires_urgent_escalation and send "
    "an [R#] URGENT summary to the top of the clinician queue.",
    alias="demo-crisis",
    turns=[
        ScriptedTurn(
            "My mood has been very low, maybe 2 out of 10. I've lost interest in almost everything, nearly "
            "every day, and I feel down nearly every day.",
            [store("mood", phq_little_interest=3, phq_feeling_down=3, overall_mood_rating=2)],
            "I'm really sorry you're feeling this way. Can I ask how hopeful you feel about things getting "
            "better?",
        ),
        # No scripted tool calls: this message must be caught deterministically before any LLM call.
        ScriptedTurn("I don't. Everything feels hopeless and I've been thinking about ending my life."),
    ],
)  # fmt: skip

# ---------------------------------------------------------------------------
# 5. Incomplete / interrupted assessment
# ---------------------------------------------------------------------------

INTERRUPTED = ExamScenario(
    number=5,
    key="interrupted",
    title="Incomplete or interrupted assessment",
    requirement="Patient completes 2 domains then asks to stop and continue later. Status must become "
    "'interrupted' with state persisted in the SQLite checkpointer; a fresh process then resumes the same "
    "session_id from the exact checkpoint.",
    alias="demo-paused",
    turns=[
        ScriptedTurn(
            "My mood is okay, around 7 out of 10. Less interest in things on several days, but I haven't "
            "really felt down. No thoughts of hurting myself.",
            [store("mood", phq_little_interest=1, phq_feeling_down=0, overall_mood_rating=7,
                   self_harm_thoughts=False)],
            "Thank you. How stressed have you been feeling, from 0 to 10, and what's causing it?",
        ),
        ScriptedTurn(
            "Stress is about 4 out of 10, mainly because of moving house.",
            [store("stress", perceived_stress_level=4, stress_triggers=["moving house"]), audit()],
            "Moving is a big change. Next, how has your sleep been?",
        ),
        # Pause intent: handled deterministically (no LLM call), status -> interrupted.
        ScriptedTurn("I need to stop here and continue later."),
    ],
    resume_turns=[
        ScriptedTurn(
            "I'm back. I sleep about 7 hours a night, good quality, and no real sleep problems.",
            [store("sleep", average_sleep_hours=7, sleep_quality="good", reports_sleep_problems=False)],
            "Welcome back, and thanks for picking up where we left off. Next, I'd like to ask about worry and "
            "feeling on edge.",
        ),
    ],
)  # fmt: skip

EXAM_SCENARIOS: list[ExamScenario] = [COMPLETE, MISSING, CONFLICTING, DISTRESS, INTERRUPTED]
