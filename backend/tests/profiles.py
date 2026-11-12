"""Reusable answer sets for tests."""

from __future__ import annotations

from typing import Any

# Complete, internally consistent answers with no risk indicators.
CALM_PROFILE: dict[str, dict[str, Any]] = {
    "mood": {"phq_little_interest": 0, "phq_feeling_down": 0, "overall_mood_rating": 8,
             "hopelessness_level": "none", "self_harm_thoughts": False},
    "stress": {"perceived_stress_level": 3, "stress_triggers": ["exams"]},
    "sleep": {"average_sleep_hours": 7.5, "sleep_quality": "good", "reports_sleep_problems": False},
    "anxiety": {"gad_nervous_anxious": 1, "gad_uncontrollable_worry": 0, "panic_attacks": "none"},
    "functioning": {"work_study_impact": "mild", "social_engagement": "normal", "energy_level": 7,
                    "self_care": "maintained"},
    "concerns": {"narrative": "Mostly fine, a bit busy with exams.", "support_goals": ["study balance"]},
}  # fmt: skip
