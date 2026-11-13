"""Non-diagnostic intake guides per domain, paraphrasing PHQ-2, GAD-2 and WHO-5 style items.

Each question names the schema `field` it fills, so the agent knows exactly what to pass to
`store_assessment_response`.
"""

from __future__ import annotations

from typing import Any

from app.schemas.assessment import AssessmentDomain

FREQUENCY_OPTIONS = {
    0: "Not at all",
    1: "Several days",
    2: "More than half the days",
    3: "Nearly every day",
}
WHO5_OPTIONS = {
    5: "All of the time",
    4: "Most of the time",
    3: "More than half of the time",
    2: "Less than half of the time",
    1: "Some of the time",
    0: "At no time",
}

COMMON_GUARDRAILS = [
    "Never diagnose, label a condition, or say the person 'has' a disorder.",
    "Never recommend, adjust or comment on medication or treatment.",
    "Ask one question at a time, in plain, warm language; reflect back before moving on.",
    "Accept 'I'd rather not say' and record nothing for that field.",
    "If the person mentions self-harm, suicide, or harming others, pause the screening and "
    "follow the safety protocol (share crisis resources, flag for immediate professional review).",
]

_GUIDES: dict[AssessmentDomain, dict[str, Any]] = {
    AssessmentDomain.MOOD: {
        "title": "Mood & emotional wellbeing",
        "instruments": ["PHQ-2 (inspired)", "WHO-5 (inspired)"],
        "opening": "I'd like to ask a few questions about how your mood has been over the last two weeks.",
        "questions": [
            {
                "field": "phq_little_interest",
                "question": "Over the last two weeks, how often have you had little interest or "
                "pleasure in doing things?",
                "response_format": FREQUENCY_OPTIONS,
            },
            {
                "field": "phq_feeling_down",
                "question": "Over the last two weeks, how often have you been feeling down, low or hopeless?",
                "response_format": FREQUENCY_OPTIONS,
            },
            {
                "field": "overall_mood_rating",
                "question": "On a scale from 1 (very low) to 10 (very good), how would you rate your mood lately?",
                "response_format": "integer 1-10",
            },
            {
                "field": "hopelessness_level",
                "question": "How hopeful do you feel about things getting better?",
                "response_format": "none | mild | moderate | severe (level of hopelessness)",
            },
            {
                "field": "self_harm_thoughts",
                "question": "Sometimes when people feel low they have thoughts that they'd be better "
                "off dead or of hurting themselves. Have you had any thoughts like that recently?",
                "response_format": "true | false",
                "safety_critical": True,
            },
            {
                "field": "who5_items",
                "question": "Optional wellbeing check, over the last two weeks: have you felt (1) cheerful "
                "and in good spirits, (2) calm and relaxed, (3) active and vigorous, (4) fresh and rested "
                "on waking, (5) that daily life is filled with things that interest you?",
                "response_format": {"list of 5 integers": WHO5_OPTIONS},
            },
            {
                "field": "mood_description",
                "question": "How would you describe your mood in your own words?",
                "response_format": "free text",
            },
        ],
    },
    AssessmentDomain.STRESS: {
        "title": "Stress levels",
        "instruments": ["Perceived stress rating (0-10)"],
        "opening": "Let's talk about stress and what's been putting pressure on you.",
        "questions": [
            {
                "field": "perceived_stress_level",
                "question": "On a scale from 0 (no stress) to 10 (the most stress you can imagine), "
                "how stressed have you felt recently?",
                "response_format": "integer 0-10",
            },
            {
                "field": "stress_triggers",
                "question": "What are the main things causing you stress right now?",
                "response_format": "list of short phrases",
            },
            {
                "field": "stress_duration",
                "question": "How long have you been feeling this level of stress?",
                "response_format": "days | weeks | months | years",
            },
            {
                "field": "feels_overwhelmed",
                "question": "Do you often feel overwhelmed or unable to cope?",
                "response_format": "true | false",
            },
            {
                "field": "coping_strategies",
                "question": "What, if anything, helps you when you're stressed?",
                "response_format": "list of short phrases",
            },
        ],
    },
    AssessmentDomain.SLEEP: {
        "title": "Sleep patterns",
        "instruments": ["Sleep self-report"],
        "opening": "Sleep affects how we feel a lot, so I'd like to ask about yours.",
        "questions": [
            {
                "field": "average_sleep_hours",
                "question": "On a typical night, about how many hours do you sleep?",
                "response_format": "number of hours",
            },
            {
                "field": "sleep_quality",
                "question": "How would you rate the quality of your sleep?",
                "response_format": "very_poor | poor | fair | good | very_good",
            },
            {
                "field": "reports_sleep_problems",
                "question": "Do you feel you have any problems with your sleep?",
                "response_format": "true | false",
            },
            {
                "field": "difficulty_falling_asleep",
                "question": "Do you have trouble falling asleep?",
                "response_format": "true | false",
            },
            {
                "field": "frequent_night_waking",
                "question": "Do you wake up often during the night?",
                "response_format": "true | false",
            },
            {
                "field": "early_morning_waking",
                "question": "Do you wake much earlier than you want and can't get back to sleep?",
                "response_format": "true | false",
            },
            {
                "field": "wakes_unrefreshed",
                "question": "Do you usually wake up feeling tired or exhausted?",
                "response_format": "true | false",
            },
            {
                "field": "sleeping_more_than_usual",
                "question": "Have you been sleeping a lot more than usual?",
                "response_format": "true | false",
            },
            {
                "field": "excessive_daytime_sleepiness",
                "question": "Do you struggle to stay awake during the day?",
                "response_format": "true | false",
            },
        ],
    },
    AssessmentDomain.ANXIETY: {
        "title": "Anxiety-related experiences",
        "instruments": ["GAD-2 (inspired)"],
        "opening": "Now a few questions about worry and feeling on edge over the last two weeks.",
        "questions": [
            {
                "field": "gad_nervous_anxious",
                "question": "Over the last two weeks, how often have you felt nervous, anxious or on edge?",
                "response_format": FREQUENCY_OPTIONS,
            },
            {
                "field": "gad_uncontrollable_worry",
                "question": "Over the last two weeks, how often have you been unable to stop or control worrying?",
                "response_format": FREQUENCY_OPTIONS,
            },
            {
                "field": "panic_attacks",
                "question": "Have you had sudden episodes of intense fear or panic, like a racing heart or "
                "trouble breathing? How often?",
                "response_format": "none | occasional | frequent | severe",
            },
            {
                "field": "physical_symptoms",
                "question": "Do you notice physical signs when anxious (e.g. racing heart, tension, stomach upset)?",
                "response_format": "list of short phrases",
            },
            {
                "field": "cognitive_symptoms",
                "question": "What goes through your mind when anxious (e.g. racing thoughts, expecting the worst)?",
                "response_format": "list of short phrases",
            },
            {
                "field": "avoidance_behaviours",
                "question": "Have you been avoiding places, people or situations because of anxiety?",
                "response_format": "true | false",
            },
        ],
    },
    AssessmentDomain.FUNCTIONING: {
        "title": "Daily activities & functioning",
        "instruments": ["Functional impact self-report"],
        "opening": "I'd like to understand how you've been managing day to day.",
        "questions": [
            {
                "field": "work_study_impact",
                "question": "How much have these feelings affected your work or studies?",
                "response_format": "none | mild | moderate | severe",
            },
            {
                "field": "days_missed_last_month",
                "question": "In the past month, about how many days of work or study have you missed?",
                "response_format": "integer 0-31",
            },
            {
                "field": "social_engagement",
                "question": "How has your contact with friends and family been?",
                "response_format": "normal | reduced | minimal | isolated",
            },
            {
                "field": "energy_level",
                "question": "On a scale from 1 to 10, how is your energy most days?",
                "response_format": "integer 1-10",
            },
            {
                "field": "self_care",
                "question": "Have you been able to keep up with things like eating, washing and household tasks?",
                "response_format": "maintained | somewhat_neglected | significantly_neglected",
            },
        ],
    },
    AssessmentDomain.CONCERNS: {
        "title": "Personal concerns & reported challenges",
        "instruments": ["Open narrative"],
        "opening": "Finally, I'd like to hear in your own words what's been going on.",
        "questions": [
            {
                "field": "narrative",
                "question": "Is there anything you'd like to share about what you've been going through?",
                "response_format": "free text",
            },
            {
                "field": "main_challenges",
                "question": "What feel like the biggest challenges right now?",
                "response_format": "list of short phrases",
            },
            {
                "field": "support_goals",
                "question": "What would you most like to get from support, or what would 'feeling better' look like?",
                "response_format": "list of short phrases",
            },
            {
                "field": "currently_receiving_support",
                "question": "Are you currently seeing anyone for support, like a counsellor or doctor?",
                "response_format": "true | false",
            },
        ],
    },
}


def get_domain_guide(domain: AssessmentDomain) -> dict[str, Any]:
    return {"domain": domain.value, **_GUIDES[domain], "guardrails": COMMON_GUARDRAILS}


def field_prompt(domain: AssessmentDomain, field: str) -> str:
    for question in _GUIDES[domain]["questions"]:
        if question["field"] == field:
            return question["question"]
    return f"Ask about {field.replace('_', ' ')}."
