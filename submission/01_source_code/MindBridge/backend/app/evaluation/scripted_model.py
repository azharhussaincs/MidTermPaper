"""Deterministic chat model for offline runs: tests, CI grading and the exam scenario runner.

`ScriptedChatModel` delegates every call to a `responder(messages) -> AIMessage` function and
records the messages it received. `bind_tools` returns itself, so LangChain's default
`with_structured_output` works: structured-output calls are answered with a tool call named
after the schema (`SummaryNarrative`, `ReflectionVerdict`).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

Responder = Callable[[list[BaseMessage]], AIMessage]


class ScriptedChatModel(BaseChatModel):
    responder: Responder
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.responder(list(messages)))])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:  # type: ignore[override]
        return self

    def calls_for(self, role: str) -> list[list[BaseMessage]]:
        return [c for c in self.calls if role_of(c) == role]


def role_of(messages: list[BaseMessage]) -> str:
    """Which prompt is being run, read from the system prompt's '# Role:' header."""
    first = messages[0] if messages else None
    content = str(first.content) if isinstance(first, SystemMessage) else ""
    for marker, role in (
        ("Role: Intake Interviewer", "interviewer"),
        ("Role: Clinical Summary Writer", "summary"),
        ("Role: Clinical Summary Reviewer", "reflection"),
    ):
        if marker in content:
            return role
    return "unknown"


def tool_call(name: str, **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}


def structured(schema_name: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[tool_call(schema_name, **args)])


# ---------------------------------------------------------------------------
# Scenario scripting
# ---------------------------------------------------------------------------

_FREQUENCY = ["not at all", "on several days", "on more than half the days", "nearly every day"]


@dataclass(frozen=True)
class ScriptedTurn:
    """One patient message and what a well-behaved interviewer model does with it."""

    user: str
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    reply: str = "Thank you for sharing that. Could you tell me a little more?"


def _phrase(value: str) -> str:
    return value.replace("_", " ")


def compose_narrative(data: dict[str, Any]) -> str:
    """Neutral, attributed, non-diagnostic description of what the person reported."""
    parts: list[str] = []
    mood, stress, sleep = data.get("mood") or {}, data.get("stress") or {}, data.get("sleep") or {}
    anxiety, functioning, concerns = (
        data.get("anxiety") or {},
        data.get("functioning") or {},
        data.get("concerns") or {},
    )

    if mood:
        bits = []
        if "overall_mood_rating" in mood:
            bits.append(f"rates their mood {mood['overall_mood_rating']}/10")
        if "phq_little_interest" in mood:
            bits.append(f"reports reduced interest {_FREQUENCY[mood['phq_little_interest']]}")
        if "phq_feeling_down" in mood:
            bits.append(f"feeling down {_FREQUENCY[mood['phq_feeling_down']]}")
        if mood.get("hopelessness_level") not in (None, "none"):
            bits.append(f"{mood['hopelessness_level']} hopelessness")
        parts.append("The person " + ", ".join(bits) + ".")
    if stress:
        text = f"They describe stress at {stress.get('perceived_stress_level', '?')}/10"
        if stress.get("stress_triggers"):
            text += f", linked to {', '.join(stress['stress_triggers'])}"
        parts.append(text + ".")
    if sleep:
        text = f"They report sleeping about {sleep.get('average_sleep_hours', '?')} hours a night"
        if "sleep_quality" in sleep:
            text += f" with {_phrase(sleep['sleep_quality'])} sleep quality"
        parts.append(text + ".")
    if anxiety:
        bits = []
        if "gad_nervous_anxious" in anxiety:
            bits.append(f"feeling on edge {_FREQUENCY[anxiety['gad_nervous_anxious']]}")
        if anxiety.get("panic_attacks") not in (None, "none"):
            bits.append(f"{anxiety['panic_attacks']} panic attacks")
        if bits:
            parts.append("They report " + " and ".join(bits) + ".")
    if functioning:
        bits = []
        if "work_study_impact" in functioning:
            bits.append(f"a {functioning['work_study_impact']} impact on work or study")
        if "social_engagement" in functioning:
            bits.append(f"{_phrase(functioning['social_engagement'])} social contact")
        if "energy_level" in functioning:
            bits.append(f"energy around {functioning['energy_level']}/10")
        parts.append("Day to day they describe " + ", ".join(bits) + ".")
    if concerns.get("support_goals"):
        parts.append(f"They would like support with: {', '.join(concerns['support_goals'])}.")
    return " ".join(parts) or "No self-reported information was collected before the session ended."


_TAG_LINE = re.compile(r"^(\[([MIR])\d+\]) (.+)$", re.MULTILINE)
_RECORD = re.compile(
    r"# Stored screening record \(self-reported\)\n(.*?)\n\n# Deterministic audit results", re.DOTALL
)


def scripted_summary(messages: list[BaseMessage]) -> dict[str, Any]:
    """A well-behaved summary writer: neutral narrative + every audit tag, urgent risks marked."""
    request = str(messages[-1].content)
    record = _RECORD.search(request)
    data = json.loads(record.group(1)) if record else {}
    tags = _TAG_LINE.findall(request.split("# Your previous draft was REJECTED")[0])
    return {
        "reported_concerns_summary": compose_narrative(data),
        "missing_or_inconsistent_info": [f"{tag} {text}" for tag, kind, text in tags if kind in "MI"],
        "areas_requiring_professional_review": [
            f"{tag} {'URGENT: ' if text.startswith(('CRITICAL', 'HIGH')) else ''}{text}"
            for tag, kind, text in tags
            if kind == "R"
        ],
    }


class ScenarioResponder:
    """Plays the interviewer, summary writer and reviewer for a scripted scenario.

    The interviewer turn is identified by the latest patient message (not by counting
    messages), so it stays correct when history is trimmed or the session is resumed.
    """

    def __init__(self, turns: Sequence[ScriptedTurn]) -> None:
        self.by_message = {turn.user: turn for turn in turns}

    def __call__(self, messages: list[BaseMessage]) -> AIMessage:
        role = role_of(messages)
        if role == "summary":
            return structured("SummaryNarrative", **scripted_summary(messages))
        if role == "reflection":
            return structured("ReflectionVerdict", passed=True)
        last_user = next((str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        turn = self.by_message.get(last_user)
        if turn and turn.tool_calls and isinstance(messages[-1], HumanMessage):
            return AIMessage(
                content="", tool_calls=[tool_call(name, **args) for name, args in turn.tool_calls]
            )
        return AIMessage(content=turn.reply if turn else "Thank you. Could you tell me a little more?")
