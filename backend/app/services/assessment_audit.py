"""Deterministic audit of collected domain data: completeness, inconsistencies, risk.

Pure functions over `AssessmentDomainData` — no DB, no LLM — so they are fast, testable and
cannot be talked out of a risk flag. Free-text matching is deliberately conservative: any
self-harm or harm-to-others mention escalates unless it is an explicit, narrow denial
("no thoughts of hurting myself", "I would never hurt myself"). Ambiguous phrasing such as
"I haven't stopped thinking about suicide" or "I don't want to wake up" always escalates.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.questionnaires.guides import field_prompt
from app.schemas.assessment import (
    REQUIRED_FIELDS,
    AssessmentDomain,
    AssessmentDomainData,
    CompletionStatus,
    Inconsistency,
    MissingField,
    RiskFlag,
)

D = AssessmentDomain

# ---------------------------------------------------------------------------
# Free-text distress lexicon
# ---------------------------------------------------------------------------

_SELF_HARM = re.compile(
    r"\b(suicid\w*|kill(ing)? myself|end(ing)? (my|it) (life|all)|take my (own )?life|"
    r"self[- ]?harm\w*|hurt(ing)? myself|cut(ting)? myself|better off dead|"
    r"(don'?t|do not) want to (live|be alive|wake up)|no reason to live|overdos\w*)\b",
    re.IGNORECASE,
)
_HARM_OTHERS = re.compile(r"\b(hurt|harm|kill)(ing)? (someone|somebody|others|him|her|them)\b", re.IGNORECASE)
_HOPELESSNESS = re.compile(
    r"\b(hopeless\w*|no hope|worthless|can'?t go on|nothing will (ever )?(get|be) better|"
    r"no point( in)? (anything|living|trying)|give up on (life|everything)|trapped)\b",
    re.IGNORECASE,
)
_PANIC = re.compile(
    r"\b(panic attacks?|can'?t breathe|feel(ing)? like i'?m dying|heart (is )?racing)\b", re.IGNORECASE
)

ESCALATE = "Pause screening, share crisis resources, and route to a clinician immediately."
REVIEW = "Highlight for clinician review in the summary."


def _iter_text(data: AssessmentDomainData) -> Iterator[tuple[D, str]]:
    for domain in D:
        for value in data.domain(domain).model_dump().values():
            if isinstance(value, str):
                yield domain, value
            elif isinstance(value, list):
                yield from ((domain, item) for item in value if isinstance(item, str))


def _quote(text: str, match: re.Match[str], width: int = 60) -> str:
    start, end = max(match.start() - width, 0), min(match.end() + width, len(text))
    return f"...{text[start:end].strip()}..." if (start or end < len(text)) else text


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def missing_fields(data: AssessmentDomainData) -> list[MissingField]:
    missing: list[MissingField] = []
    for domain, fields in REQUIRED_FIELDS.items():
        model = data.domain(domain)
        for name in fields:
            value = getattr(model, name)
            if value is None or (isinstance(value, (str, list)) and len(value) == 0):
                missing.append(
                    MissingField(domain=domain, field=name, prompt_hint=field_prompt(domain, name))
                )
    return missing


def completion_percentage(data: AssessmentDomainData) -> float:
    total = sum(len(fields) for fields in REQUIRED_FIELDS.values())
    return round(100 * (total - len(missing_fields(data))) / total, 1)


def domain_completion(data: AssessmentDomainData) -> tuple[list[D], list[D]]:
    pending = {m.domain for m in missing_fields(data)}
    return [d for d in D if d not in pending], [d for d in D if d in pending]


def domain_completion_map(data: AssessmentDomainData) -> dict[str, dict[str, Any]]:
    """Per-domain progress for progress bars: required fields answered vs total."""
    missing_by_domain: dict[D, int] = {}
    for item in missing_fields(data):
        missing_by_domain[item.domain] = missing_by_domain.get(item.domain, 0) + 1
    result: dict[str, dict[str, Any]] = {}
    for domain, fields in REQUIRED_FIELDS.items():
        answered = len(fields) - missing_by_domain.get(domain, 0)
        result[domain.value] = {
            "completed": answered == len(fields),
            "answered": answered,
            "required": len(fields),
            "percentage": round(100 * answered / len(fields), 1),
        }
    return result


def highest_risk_level(flags: list[dict[str, Any]]) -> str:
    """'critical' | 'high' | 'elevated' | 'none' for a list of serialised risk flags."""
    levels = {flag.get("level") for flag in flags}
    return next((level for level in ("critical", "high", "elevated") if level in levels), "none")


def completion_status(data: AssessmentDomainData, status: str) -> CompletionStatus:
    completed, pending = domain_completion(data)
    return CompletionStatus(
        percentage=completion_percentage(data),
        completed_domains=completed,
        pending_domains=pending,
        status=status,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Inconsistencies
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Scores:
    phq2: int | None
    gad2: int | None


def _scores(data: AssessmentDomainData) -> _Scores:
    m, a = data.mood, data.anxiety
    phq2 = (
        None
        if None in (m.phq_little_interest, m.phq_feeling_down)
        else m.phq_little_interest + m.phq_feeling_down
    )
    gad2 = (
        None
        if None in (a.gad_nervous_anxious, a.gad_uncontrollable_worry)
        else a.gad_nervous_anxious + a.gad_uncontrollable_worry
    )
    return _Scores(phq2, gad2)  # type: ignore[arg-type]


_SELF_RATINGS = {
    "overall_mood_rating", "perceived_stress_level", "energy_level", "hopelessness_level",
    "phq_little_interest", "phq_feeling_down", "gad_nervous_anxious", "gad_uncontrollable_worry",
}  # fmt: skip
_UNITS = {
    "overall_mood_rating": "/10",
    "perceived_stress_level": "/10",
    "energy_level": "/10",
    "average_sleep_hours": "h",
}


def _fmt_answer(field: str, value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value.replace("_", " ")
    return f"{value:g}{_UNITS.get(field, '')}"


def find_inconsistencies(
    data: AssessmentDomainData, revisions: Sequence[Mapping[str, Any]] = ()
) -> list[Inconsistency]:
    """Contradictions in the current answers, plus those an overwritten answer would hide.

    `revisions` (AssessmentRecord.answer_revisions) lists stored answers that were later
    replaced. The rules also run on the answers as first given, and every changed answer is
    listed itself, so a clinician sees "stress 0/10" even if the interviewer later stored 10/10.
    """
    found = _rule_inconsistencies(data)
    first: dict[tuple[str, str], Any] = {}
    for rev in revisions:
        first.setdefault((rev["domain"], rev["field"]), rev["previous"])
    changed = {
        key: original
        for key, original in first.items()
        if getattr(data.domain(D(key[0])), key[1]) != original
    }
    if not changed:
        return found

    raw = data.model_dump(mode="json")
    for (domain, field), original in changed.items():
        raw[domain][field] = original
    codes = {item.code for item in found}
    found += [
        item
        for item in _rule_inconsistencies(AssessmentDomainData.model_validate(raw))
        if item.code not in codes
    ]

    for (domain, field), original in changed.items():
        current = getattr(data.domain(D(domain)), field)
        name = field.replace("_", " ").capitalize()
        found.append(
            Inconsistency(
                code=f"changed_{field}",
                domains=[D(domain)],
                description=f"{name} first given as {_fmt_answer(field, original)} but later stored as {_fmt_answer(field, current)}.",
                severity="high" if field in _SELF_RATINGS else "medium",
            )
        )
    return found


def _rule_inconsistencies(data: AssessmentDomainData) -> list[Inconsistency]:
    m, st, sl, a, f = data.mood, data.stress, data.sleep, data.anxiety, data.functioning
    scores = _scores(data)
    found: list[Inconsistency] = []

    def add(code: str, domains: list[D], description: str, severity: str) -> None:
        found.append(Inconsistency(code=code, domains=domains, description=description, severity=severity))  # type: ignore[arg-type]

    if st.perceived_stress_level is not None and st.perceived_stress_level <= 2:
        acute = []
        if a.panic_attacks in ("frequent", "severe"):
            acute.append(f"{a.panic_attacks} panic attacks")
        if sl.average_sleep_hours is not None and sl.average_sleep_hours <= 4:
            acute.append(f"{sl.average_sleep_hours:g}h sleep")
        if scores.gad2 is not None and scores.gad2 >= 4:
            acute.append(f"GAD-2 style score {scores.gad2}/6")
        if acute:
            add(
                "low_stress_vs_acute_symptoms",
                [D.STRESS, D.ANXIETY, D.SLEEP],
                f"Reported stress {st.perceived_stress_level}/10 but also {', '.join(acute)}.",
                "high",
            )

    if m.overall_mood_rating is not None and m.overall_mood_rating >= 8:
        distress = []
        if scores.phq2 is not None and scores.phq2 >= 4:
            distress.append(f"PHQ-2 style score {scores.phq2}/6")
        if m.hopelessness_level in ("moderate", "severe"):
            distress.append(f"{m.hopelessness_level} hopelessness")
        if m.self_harm_thoughts:
            distress.append("thoughts of self-harm")
        if a.panic_attacks in ("frequent", "severe"):
            distress.append(f"{a.panic_attacks} panic attacks")
        if distress:
            add(
                "positive_mood_vs_distress",
                [D.MOOD, D.ANXIETY],
                f"Rated mood {m.overall_mood_rating}/10 but also reported {', '.join(distress)}.",
                "high",
            )

    if sl.reports_sleep_problems is False:
        symptoms = [
            label
            for label, present in (
                ("waking up exhausted", sl.wakes_unrefreshed),
                ("difficulty falling asleep", sl.difficulty_falling_asleep),
                ("frequent night waking", sl.frequent_night_waking),
                ("early morning waking", sl.early_morning_waking),
                ("sleeping more than usual", sl.sleeping_more_than_usual),
            )
            if present
        ]
        if sl.average_sleep_hours is not None and sl.average_sleep_hours < 5:
            symptoms.append(f"only {sl.average_sleep_hours:g}h sleep")
        if sl.sleep_quality in ("poor", "very_poor"):
            symptoms.append(f"{sl.sleep_quality.replace('_', ' ')} sleep quality")
        if symptoms:
            add(
                "no_sleep_issues_vs_symptoms",
                [D.SLEEP],
                f"Said they have no sleep problems but reported {', '.join(symptoms)}.",
                "medium",
            )

    if (
        sl.sleep_quality in ("good", "very_good")
        and sl.average_sleep_hours is not None
        and sl.average_sleep_hours < 5
    ):
        add(
            "good_quality_vs_short_sleep",
            [D.SLEEP],
            f"Rated sleep quality {sl.sleep_quality.replace('_', ' ')} on {sl.average_sleep_hours:g}h a night.",
            "low",
        )

    if scores.gad2 == 0 and a.panic_attacks in ("frequent", "severe"):
        add(
            "no_anxiety_vs_panic",
            [D.ANXIETY],
            f"Anxiety and worry rated 'not at all' but {a.panic_attacks} panic attacks reported.",
            "medium",
        )

    if f.work_study_impact == "none" and (f.days_missed_last_month or 0) >= 5:
        add(
            "no_impact_vs_missed_days",
            [D.FUNCTIONING],
            f"No reported work/study impact but {f.days_missed_last_month} days missed last month.",
            "medium",
        )

    if m.hopelessness_level == "none":
        for domain, text in _iter_text(data):
            if match := _HOPELESSNESS.search(text):
                add(
                    "no_hopelessness_vs_narrative",
                    [D.MOOD, domain],
                    f"Hopelessness rated 'none' but they wrote: {_quote(text, match)}",
                    "medium",
                )
                break

    return found


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------


_TEXT_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("self_harm_language", _SELF_HARM, "critical"),
    ("harm_to_others_language", _HARM_OTHERS, "critical"),
    ("hopelessness_language", _HOPELESSNESS, "high"),
    ("panic_language", _PANIC, "elevated"),
)


# An explicit denial immediately before the match: "no / never ...", or "(have) no / never /
# haven't had / without (any) thoughts|ideas|plans|urges of|about ...". Deliberately narrow:
# "not", "haven't stopped", "not sure" etc. are NOT denials.
_DENIAL_BEFORE = re.compile(
    r"(\b(no|never)\s+$)"
    r"|(\b(no|never|without|haven'?t had|have not had|hasn'?t had|never had|deny having|denies having)"
    r"\s+(any\s+)?(thoughts?|ideas?|plans?|urges?|intentions?)\s+(of|about)\s+$)",
    re.IGNORECASE,
)
# Hopelessness wording is never treated as denied ("no hope" is itself a risk phrase).
_DENIABLE = {"self_harm_language", "harm_to_others_language", "panic_language"}


def _is_denied(text: str, match: re.Match[str]) -> bool:
    sentence_start = max(text.rfind(sep, 0, match.start()) for sep in ".!?;\n") + 1
    return bool(_DENIAL_BEFORE.search(text[sentence_start : match.start()]))


def scan_text_for_risk(text: str, domain: D = D.CONCERNS, *, source: str = "Wrote") -> list[RiskFlag]:
    """Lexicon scan of one piece of free text; critical matches require immediate escalation.

    Every match is considered, so "I'd never hurt myself... but last night I cut myself"
    still escalates on the second mention.
    """
    flags: list[RiskFlag] = []
    for code, pattern, level in _TEXT_RISK_PATTERNS:
        matches = [m for m in pattern.finditer(text) if code not in _DENIABLE or not _is_denied(text, m)]
        if match := next(iter(matches), None):
            escalate = level == "critical"
            flags.append(
                RiskFlag(
                    code=code,
                    level=level,  # type: ignore[arg-type]
                    domain=domain,
                    evidence=f"{source}: {_quote(text, match)}",
                    requires_immediate_escalation=escalate,
                    recommended_action=ESCALATE if escalate else REVIEW,
                )
            )
    return flags


# ---------------------------------------------------------------------------
# Answers to the safety question
# ---------------------------------------------------------------------------

# Wording of the guide's self-harm question and the interviewer's paraphrases of it.
_SELF_HARM_TOPIC = re.compile(
    r"\b((hurt|harm|kill)(ing)? (yourself|themselves)|better off (dead|not (being )?(here|around|alive))|"
    r"end(ing)? (your|their) (own )?life|suicid\w*|self[- ]?harm\w*)",
    re.IGNORECASE,
)
_YES_NO_ABOUT_THOUGHTS = re.compile(
    r"^(have|has|do|did|are|were|is)\b.*\b(thoughts?|thought|thinking|felt|feel|feeling|considered|urges?)\b",
    re.IGNORECASE,
)
# Only an explicit "no" is a denial. Same policy as the free-text scan: ambiguous answers escalate.
_EXPLICIT_NO = re.compile(
    r"^\s*(no|nope|never|not at all|none|i (have )?never|i haven'?t|i have not|not once)\b", re.IGNORECASE
)
_CONTRAST = re.compile(
    r"\b(but|although|though|except|sometimes|occasionally|maybe|yes|used to|once|before)\b", re.IGNORECASE
)
_DECLINED = re.compile(
    r"^\s*(i'?d rather not (say|answer)|i would rather not|prefer not to (say|answer)|skip|pass)\b",
    re.IGNORECASE,
)


def scan_safety_answer(question: str, reply: str) -> list[RiskFlag]:
    """A reply to the self-harm question that is not an explicit "no" is a disclosure.

    The structured `self_harm_thoughts` answer is normally stored by the model; this makes the
    escalation independent of it, so "Sometimes" or "not sure" can never slip through if the model
    files the answer wrongly or not at all. Declining to answer raises nothing here: the question
    then stays unanswered and is listed for the clinician as missing.
    """
    asked = [q.strip() for q in re.findall(r"[^.?!]*\?", question)]
    if not asked or not _YES_NO_ABOUT_THOUGHTS.match(asked[-1]) or not _SELF_HARM_TOPIC.search(question):
        return []
    text = reply.strip()
    if not text or _DECLINED.match(text) or (_EXPLICIT_NO.match(text) and not _CONTRAST.search(text)):
        return []
    return [
        RiskFlag(
            code="self_harm_thoughts",
            level="critical",
            domain=D.MOOD,
            evidence=f'Answered "{text[:120]}" when asked about thoughts of self-harm.',
            requires_immediate_escalation=True,
            recommended_action=ESCALATE,
        )
    ]


def find_risk_flags(data: AssessmentDomainData) -> list[RiskFlag]:
    m, st, sl, a, f = data.mood, data.stress, data.sleep, data.anxiety, data.functioning
    scores = _scores(data)
    flags: list[RiskFlag] = []

    def add(code: str, level: str, domain: D, evidence: str, escalate: bool) -> None:
        flags.append(
            RiskFlag(
                code=code, level=level, domain=domain, evidence=evidence,  # type: ignore[arg-type]
                requires_immediate_escalation=escalate, recommended_action=ESCALATE if escalate else REVIEW,
            )
        )  # fmt: skip

    # Safety-critical
    if m.self_harm_thoughts:
        add(
            "self_harm_thoughts",
            "critical",
            D.MOOD,
            "Reported thoughts of self-harm or being better off dead.",
            True,
        )
    seen_text: set[str] = set()
    for domain, text in _iter_text(data):
        for flag in scan_text_for_risk(text, domain):
            if flag.code not in seen_text:
                seen_text.add(flag.code)
                flags.append(flag)

    # Structured indicators
    if m.hopelessness_level == "severe":
        add("severe_hopelessness", "high", D.MOOD, "Self-rated hopelessness: severe.", True)
    elif m.hopelessness_level == "moderate":
        add("moderate_hopelessness", "elevated", D.MOOD, "Self-rated hopelessness: moderate.", False)
    if scores.phq2 is not None and scores.phq2 >= 3:
        add("phq2_positive_screen", "elevated", D.MOOD, f"PHQ-2 style score {scores.phq2}/6 (>=3).", False)
    if m.who5_items is not None and sum(m.who5_items) * 4 <= 28:
        add(
            "low_wellbeing_index",
            "elevated",
            D.MOOD,
            f"WHO-5 style index {sum(m.who5_items) * 4}/100 (<=28).",
            False,
        )

    if scores.gad2 is not None and scores.gad2 >= 3:
        add("gad2_positive_screen", "elevated", D.ANXIETY, f"GAD-2 style score {scores.gad2}/6 (>=3).", False)
    if a.panic_attacks == "severe":
        add("severe_panic", "high", D.ANXIETY, "Reports severe panic attacks.", True)
    elif a.panic_attacks == "frequent":
        add("frequent_panic", "high", D.ANXIETY, "Reports frequent panic attacks.", False)

    if st.perceived_stress_level is not None and st.perceived_stress_level >= 9:
        add(
            "extreme_stress", "elevated", D.STRESS, f"Perceived stress {st.perceived_stress_level}/10.", False
        )

    if sl.average_sleep_hours is not None and sl.average_sleep_hours < 4:
        add(
            "severe_sleep_deprivation", "high", D.SLEEP, f"Averages {sl.average_sleep_hours:g}h sleep.", False
        )
    elif sl.average_sleep_hours is not None and sl.average_sleep_hours >= 12:
        add(
            "hypersomnia_indicator",
            "elevated",
            D.SLEEP,
            f"Averages {sl.average_sleep_hours:g}h sleep.",
            False,
        )

    if f.work_study_impact == "severe" and f.self_care == "significantly_neglected":
        add(
            "extreme_functional_impairment",
            "high",
            D.FUNCTIONING,
            "Severe work/study impact with significantly neglected self-care.",
            True,
        )
    elif (
        f.work_study_impact == "severe"
        or f.self_care == "significantly_neglected"
        or f.social_engagement == "isolated"
    ):
        add(
            "functional_impairment",
            "elevated",
            D.FUNCTIONING,
            f"work/study impact={f.work_study_impact}, self-care={f.self_care}, social={f.social_engagement}.",
            False,
        )

    order = {"critical": 0, "high": 1, "elevated": 2}
    return sorted(flags, key=lambda flag: order[flag.level])
