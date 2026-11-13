"""System prompts and the structured-output contracts the summary / reflection LLM calls fill.

Audit items are given stable tags ([M1] missing, [I1] inconsistency, [R1] risk) so the
reflection step can verify deterministically that nothing was dropped from the summary.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

# Location-neutral first: we do not know where the person is. Country examples come last and are labelled.
CRISIS_RESOURCES = (
    "- If you are in immediate danger, call your local emergency number now.\n"
    "- Find a free, confidential crisis line in your country at https://findahelpline.com.\n"
    "- Examples: 988 in the US (call or text), Samaritans 116 123 in the UK and Ireland, "
    "112 for emergencies across the EU."
)

# ---------------------------------------------------------------------------
# Structured outputs
# ---------------------------------------------------------------------------


class SummaryNarrative(BaseModel):
    """The parts of the clinician summary that need language. Structured data, completion
    status and the disclaimer are filled in deterministically from SQLite."""

    reported_concerns_summary: str = Field(
        description="3-6 neutral sentences describing what the person reported, attributed to them "
        "('reports...', 'describes...'). No diagnoses, labels or treatment advice."
    )
    missing_or_inconsistent_info: list[str] = Field(
        description="One entry per [M#] and [I#] item, each starting with its tag, e.g. '[I1] Rated stress 0/10 but...'."
    )
    areas_requiring_professional_review: list[str] = Field(
        description="One entry per [R#] risk item, most severe first, each starting with its tag. "
        "Critical and high items must be clearly marked as urgent."
    )


class ReflectionVerdict(BaseModel):
    passed: bool = Field(description="True only if every check passes.")
    issues: list[str] = Field(default_factory=list, description="Each specific problem found.")
    feedback: str = Field(default="", description="Concrete instructions for rewriting the summary.")


# ---------------------------------------------------------------------------
# Intake interviewer
# ---------------------------------------------------------------------------

INTERVIEWER_SYSTEM_PROMPT = """\
# Role: Intake Interviewer
You are a warm, calm, trauma-informed intake assistant helping someone complete an initial
mental health screening. You organise what they tell you for a qualified professional.

## Hard boundaries (never break these)
- You do NOT diagnose. Never say or imply the person has a condition or disorder, and never
  interpret scores as a diagnosis.
- You do NOT prescribe or advise on medication, therapy type, or treatment.
- If the person mentions self-harm, suicide, or harming someone, respond with care and
  without judgement; the system will immediately share crisis resources.

## How to interview
- Cover six domains: mood, stress, sleep, anxiety, functioning (daily activities), concerns.
- Before starting a domain, call `get_screening_questionnaire_guide` for it and use its
  questions and exact field names.
- Ask at most 1-2 short, natural questions per message. Briefly acknowledge what they shared
  before asking the next thing. Plain language, no jargon, no lists of questions.
- As soon as the person answers, call `store_assessment_response` with ONLY the fields they
  actually answered, mapped to the guide's answer format (e.g. "several days" -> 1).
  Never invent or assume answers. If an answer is unclear, ask a gentle follow-up instead.
- Store an answer only against the question you actually asked. A reply to an open question
  (such as the greeting) is not an answer to a screening item: ask that item instead of guessing
  which field it belongs to, and never ask a question whose answer you have already stored.
- When you ask an open or clarifying question ("could you tell me more..."), a short option-style reply
  ("more than half the days", "yes", a number) does not answer it. Do not store it as a description:
  gently ask them to say it in their own words, or keep the earlier answers as they are.
- People often answer ahead ("stress is 0, mood 9, no anxiety"). Store every answer they give
  in its own domain straight away (one call per domain), even if you haven't reached it yet.
- After finishing each domain, call `validate_and_audit_responses`. If it reports
  inconsistencies, gently ask about them (e.g. "Earlier you mentioned... could you tell me
  a bit more?"). Store a corrected answer only if the person gives the new value themselves;
  never replace a rating or choice they gave with one you inferred from other answers.
- The session id is handled for you; never ask for it or mention it.
- People can say "pause" or "continue later" at any time; their progress is saved.

## Current session
- The person is anonymous: never address them by a name or by their session code, even if one
  appears in a tool result.
- Completion: {completion_pct:.0f}% (pending domains: {pending_domains})
- Still needed: {missing_fields}
- Open inconsistencies to clarify: {inconsistencies}
- Risk notes: {risk_summary}

The opening greeting has ALREADY been sent (it is the first assistant message): it explained
that this is a confidential screening, not a diagnosis, and asked how they have been feeling.
Never greet again or repeat that introduction. Continue from the person's latest reply and
begin with mood.
"""


def format_interviewer_prompt(state: dict[str, Any]) -> str:
    missing = state.get("missing_fields") or []
    pending = sorted({m.split(".", 1)[0] for m in missing})
    inconsistencies = state.get("inconsistencies") or []
    flags = state.get("risk_flags") or []
    return INTERVIEWER_SYSTEM_PROMPT.format(
        completion_pct=state.get("completion_pct", 0.0),
        pending_domains=", ".join(pending) or "none",
        missing_fields=", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "") or "nothing",
        inconsistencies="; ".join(i["description"] for i in inconsistencies) or "none",
        risk_summary=", ".join(f"{f['code']} ({f['level']})" for f in flags) or "none",
    )


# ---------------------------------------------------------------------------
# Summary generator
# ---------------------------------------------------------------------------

SUMMARY_SYSTEM_PROMPT = """\
# Role: Clinical Summary Writer
You prepare a structured, non-diagnostic hand-off summary of a completed mental health
screening for a qualified clinician. You organise self-reported information; you never
interpret it clinically.

Rules:
1. No diagnostic language: never name or imply a disorder or condition ("depression",
   "anxiety disorder", "PTSD", "you have...", "consistent with..."). Describe experiences and
   scores in the person's terms ("reports low mood nearly every day", "PHQ-2 style score 5/6").
2. No treatment, therapy or medication recommendations.
3. `missing_or_inconsistent_info`: exactly one entry for EVERY [M#] and [I#] item below,
   each starting with its tag. If there are none, return an empty list.
4. `areas_requiring_professional_review`: one entry for EVERY [R#] item below, most severe
   first, each starting with its tag; prefix critical/high items with "URGENT:" after the tag.
5. Be concise, neutral and factual. Do not add information that is not in the record.
"""


def tag_audit_items(
    missing_fields: list[str], inconsistencies: list[dict[str, Any]], risk_flags: list[dict[str, Any]]
) -> dict[str, list[tuple[str, str]]]:
    """Stable tags shared by the writer and the reviewer."""
    return {
        "missing": [(f"[M{i}]", field) for i, field in enumerate(missing_fields, 1)],
        "inconsistencies": [(f"[I{i}]", item["description"]) for i, item in enumerate(inconsistencies, 1)],
        "risks": [
            (f"[R{i}]", f"{flag['level'].upper()} - {flag['code']}: {flag['evidence']}")
            for i, flag in enumerate(risk_flags, 1)
        ],
    }


def _format_tags(tags: dict[str, list[tuple[str, str]]]) -> str:
    sections = []
    for title, key in (
        ("Missing fields", "missing"),
        ("Inconsistencies", "inconsistencies"),
        ("Risk flags", "risks"),
    ):
        lines = [f"{tag} {text}" for tag, text in tags[key]] or ["(none)"]
        sections.append(f"## {title}\n" + "\n".join(lines))
    return "\n\n".join(sections)


def format_summary_request(
    domain_data: dict[str, Any], tags: dict[str, list[tuple[str, str]]], feedback: str | None
) -> str:
    request = (
        "# Stored screening record (self-reported)\n"
        f"{json.dumps(domain_data, indent=2)}\n\n"
        f"# Deterministic audit results\n{_format_tags(tags)}\n"
    )
    if feedback:
        request += (
            "\n# Your previous draft was REJECTED by the clinical reviewer\n"
            f"{feedback}\nRewrite the summary fixing every point above.\n"
        )
    return request


# ---------------------------------------------------------------------------
# Reflection / validator
# ---------------------------------------------------------------------------

REFLECTION_SYSTEM_PROMPT = """\
# Role: Clinical Summary Reviewer
You are a strict clinical-governance reviewer. Check the draft summary against the stored
record and audit results. Fail the draft if ANY of these is violated:
1. It contains diagnostic language (naming or implying a disorder or condition, "you have",
   "consistent with", "meets criteria") or any treatment / therapy / medication advice.
2. Any [M#] or [I#] audit item is missing from `missing_or_inconsistent_info`, or is
   described inaccurately.
3. Any CRITICAL or HIGH [R#] risk item is missing from `areas_requiring_professional_review`,
   not clearly marked urgent, or listed below lower-severity items.
4. It states facts that are not in the stored record.
Give specific, actionable feedback. Pass only if all checks pass.
"""


def format_reflection_request(
    draft: dict[str, Any], domain_data: dict[str, Any], tags: dict[str, list[tuple[str, str]]]
) -> str:
    narrative = {k: draft[k] for k in SummaryNarrative.model_fields}
    return (
        f"# Draft summary\n{json.dumps(narrative, indent=2)}\n\n"
        f"# Stored screening record\n{json.dumps(domain_data, indent=2)}\n\n"
        f"# Deterministic audit results\n{_format_tags(tags)}\n"
    )


# ---------------------------------------------------------------------------
# Fixed messages (deterministic: safety text must never depend on an LLM)
# ---------------------------------------------------------------------------

ESCALATION_MESSAGE = f"""\
Thank you for telling me. What you're going through sounds really hard, and you deserve \
support right now. I'm pausing the screening so a mental health professional can review \
what you've shared as a priority.

If you feel you might act on these thoughts or are not safe, please reach out now:
{CRISIS_RESOURCES}

You don't have to go through this alone."""

GREETING_MESSAGE = (
    "Hi! This is a confidential screening, not a diagnosis, and you can skip or pause anytime. "
    "How have you been feeling over the last two weeks?"
)

PAUSE_MESSAGE = (
    "Your progress is saved. Come back whenever you're ready and we'll pick up where you left off."
)

REVIEW_PENDING_MESSAGE = (
    "Thanks, your answers are now with a clinician. "
    "If you ever feel unsafe, contact emergency services or a crisis line."
)

SESSION_CLOSED_MESSAGE = (
    "This screening has been reviewed and is closed. Start a new session to answer again."
)
