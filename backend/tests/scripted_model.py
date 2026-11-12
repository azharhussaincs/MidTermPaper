"""Test-only scenario scripting on top of the shared ScriptedChatModel."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.evaluation.scripted_model import ScriptedChatModel, role_of, structured, tool_call

__all__ = ["ScriptedChatModel", "role_of", "structured", "tool_call"]


def echo_audit_summary(messages: list[BaseMessage]) -> dict[str, Any]:
    """A well-behaved summary writer: lists every audit tag from the request, urgent risks flagged."""
    request = str(messages[-1].content)
    tags = re.findall(r"^(\[([MIR])\d+\]) (.+)$", request, flags=re.MULTILINE)
    return {
        "reported_concerns_summary": "Reports a range of experiences across the screening domains.",
        "missing_or_inconsistent_info": [f"{tag} {text}" for tag, kind, text in tags if kind in "MI"],
        "areas_requiring_professional_review": [
            f"{tag} {'URGENT: ' if text.startswith(('CRITICAL', 'HIGH')) else ''}{text}"
            for tag, kind, text in tags
            if kind == "R"
        ],
    }


CLEAN_SUMMARY = {
    "reported_concerns_summary": "Reports mild, exam-related stress and wants better study balance.",
    "missing_or_inconsistent_info": [],
    "areas_requiring_professional_review": [],
}
DIAGNOSTIC_SUMMARY = {
    **CLEAN_SUMMARY,
    "reported_concerns_summary": "You have Major Depressive Disorder and should start medication.",
}


class Scenario:
    """Responder for ScriptedChatModel, configured per test.

    interviewer_plan: human-turn number -> list of (tool_name, args) to call on that turn.
    After tool results come back the interviewer replies with plain text.
    summaries / verdicts: consumed in order; the last one repeats. A summary entry may be a
    callable `(messages) -> dict` (see `echo_audit_summary`).
    """

    def __init__(self) -> None:
        self.interviewer_plan: dict[int, list[tuple[str, dict[str, Any]]]] = {}
        self.summaries: list[dict[str, Any] | Callable[[list[BaseMessage]], dict[str, Any]]] = [CLEAN_SUMMARY]
        self.verdicts: list[dict[str, Any]] = [{"passed": True}]
        self._summary_calls = 0
        self._verdict_calls = 0

    def __call__(self, messages: list[BaseMessage]) -> AIMessage:
        role = role_of(messages)
        if role == "interviewer":
            turn = sum(isinstance(m, HumanMessage) for m in messages)
            if isinstance(messages[-1], HumanMessage) and (plan := self.interviewer_plan.get(turn)):
                return AIMessage(content="", tool_calls=[tool_call(name, **args) for name, args in plan])
            return AIMessage(content=f"Interviewer reply for turn {turn}")
        if role == "summary":
            entry = self.summaries[min(self._summary_calls, len(self.summaries) - 1)]
            self._summary_calls += 1
            return structured("SummaryNarrative", **(entry(messages) if callable(entry) else entry))
        if role == "reflection":
            args = self.verdicts[min(self._verdict_calls, len(self.verdicts) - 1)]
            self._verdict_calls += 1
            return structured("ReflectionVerdict", **args)
        raise AssertionError(f"Unexpected prompt: {messages[0].content[:80]!r}")
