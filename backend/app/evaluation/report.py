"""Renders an ExamRun as a Markdown evaluation report (the midterm submission artifact)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.execution_logger import GraphRunTrace, TraceEvent
from app.evaluation.runner import Check, ExamRun, ScenarioOutcome

DOMAIN_TITLES = {
    "mood": "Mood & emotional wellbeing",
    "stress": "Stress levels",
    "sleep": "Sleep patterns",
    "anxiety": "Anxiety-related experiences",
    "functioning": "Daily activities & functioning",
    "concerns": "Personal concerns & challenges",
}


def _esc(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _tick(passed: bool) -> str:
    return "✅" if passed else "❌"


def _fmt_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def _checks_table(checks: list[Check]) -> list[str]:
    lines = ["| Result | Check | Observed |", "|---|---|---|"]
    lines += [f"| {_tick(c.passed)} | {_esc(c.name)} | {_esc(c.detail)[:160]} |" for c in checks]
    return lines


def _event_text(event: TraceEvent) -> str:
    data = event.data
    parts: list[str] = []
    if data.get("no_op"):
        parts.append("no-op (skipped: deterministic path)")
    for call in data.get("tool_calls", []):
        args = ", ".join(f"{k}={v}" for k, v in call["args"].items() if k != "data")
        if "data" in call["args"]:
            args += f"{', ' if args else ''}fields={sorted(call['args']['data'])}"
        parts.append(f"calls `{call['name']}({args})`")
    for result in data.get("tool_results", []):
        status = "ok" if result.get("ok") else f"error: {result.get('error')}"
        extra = ", ".join(f"{k}={result[k]}" for k in ("domain", "completion_percentage") if k in result)
        parts.append(f"`{result['tool']}` → {status}{' (' + extra + ')' if extra else ''}")
    if "assistant" in data:
        parts.append(f"says “{data['assistant'][:110]}”")
    for key in ("completion_pct", "requires_urgent_escalation", "reflection_passed", "reflection_attempts"):
        if key in data:
            parts.append(f"{key}={data[key]}")
    if data.get("risk_flags"):
        parts.append(f"risk_flags={data['risk_flags']}")
    if data.get("inconsistencies"):
        parts.append(f"inconsistencies={data['inconsistencies']}")
    if data.get("reflection_feedback"):
        parts.append(f"feedback: {data['reflection_feedback'][:160]}")
    if data.get("draft_summary"):
        parts.append("draft summary generated")
    if data.get("final_output"):
        parts.append(f"final_output={data['final_output']}")
    return "; ".join(parts) or "state updated"


def _trace(runs: list[GraphRunTrace]) -> list[str]:
    lines: list[str] = []
    for number, run in enumerate(runs, 1):
        path = " → ".join(run.path) or "(no graph execution)"
        lines += [f"**Run {number} · `{run.label}`** (`{run.run_id}`): {path}", ""]
        rows = ["| # | Node / decision | What happened |", "|---|---|---|"]
        for event in run.events:
            if event.kind == "node":
                rows.append(f"| {event.step} | `{event.node}` | {_esc(_event_text(event))} |")
            elif event.kind == "route":
                rows.append(f"| {event.step} | ↳ `{event.data['via']}` | → `{event.data['to']}` |")
            elif event.kind == "interrupt":
                rows.append(
                    f"| {event.step} | ⏸ `interrupt()` | clinician review gate (urgent={event.data.get('urgent')}) |"
                )
            elif event.kind == "note":
                rows.append(f"| {event.step} | note | {_esc(event.data['message'])} |")
        if len(rows) > 2:
            lines += [*rows, ""]
    return lines


def _outputs(outputs: dict[str, Any]) -> list[str]:
    lines = [f"_Source: {outputs['source']}_", "", "#### 1. Structured assessment information", ""]
    structured = outputs["structured_assessment"]
    if any(structured.values()):
        lines += ["| Domain | Self-reported answers |", "|---|---|"]
        for domain, title in DOMAIN_TITLES.items():
            answers = structured.get(domain) or {}
            text = "; ".join(f"{k}: {_fmt_value(v)}" for k, v in answers.items()) or "_not answered_"
            lines.append(f"| {title} | {_esc(text)} |")
    else:
        lines.append("_No answers stored._")

    concerns = outputs["reported_concerns_summary"]
    lines += [
        "",
        "#### 2. Summary of reported concerns",
        "",
        f"> {concerns}" if concerns else "_Not generated yet._",
    ]

    lines += ["", "#### 3. Missing or inconsistent information", ""]
    lines += [f"- {_esc(e)}" for e in outputs["missing_or_inconsistent_info"]] or ["_None._"]

    lines += ["", "#### 4. Areas requiring professional review", ""]
    lines += [f"- {_esc(e)}" for e in outputs["areas_requiring_professional_review"]] or ["_None flagged._"]

    c = outputs["completion_status"]
    lines += [
        "",
        "#### 5. Assessment completion status",
        "",
        "| Percentage | Status | Completed domains | Pending domains |",
        "|---|---|---|---|",
        f"| {c['percentage']}% | `{c['status']}` | {', '.join(c['completed_domains']) or '—'} | "
        f"{', '.join(c['pending_domains']) or '—'} |",
    ]
    if outputs.get("non_diagnostic_disclaimer"):
        lines += ["", f"_Disclaimer:_ {outputs['non_diagnostic_disclaimer']}"]
    return lines


def _scenario(o: ScenarioOutcome) -> list[str]:
    s = o.scenario
    state = o.final_state
    lines = [
        f"## Scenario {s.number} — {s.title} {_tick(o.passed)}",
        "",
        f"**Exam requirement:** {s.requirement}",
        "",
        f"**Session:** `{o.session_id}` · alias `{s.alias}` · final status `{state['status']}` · "
        f"urgent escalation `{state['requires_urgent_escalation']}`",
        "",
    ]
    lines += [f"> ⚠️ {note}" for note in o.notes]
    lines += ["### Verification", "", *_checks_table(o.checks), ""]

    if "after_pause" in o.snapshots:
        lines += [
            "### Checkpoint persistence",
            "",
            "| Snapshot | Status | Completion | Messages | Next nodes |",
            "|---|---|---|---|---|",
        ]
        for label in ("after_pause", "fresh_process"):
            snap = o.snapshots.get(label)
            if snap:
                name = f"{label} (pid {snap['pid']})" if "pid" in snap else label
                lines.append(
                    f"| {name} | `{snap['status']}` | {snap['completion_pct']}% | {snap['message_count']} | "
                    f"{snap['next_nodes'] or '[]'} |"
                )
        lines.append("")

    lines += ["### Conversation", ""]
    for role, text, _ts in o.transcript:
        speaker = "**Patient:**" if role == "user" else "**Agent:**"
        lines.append(f"{speaker} {text.replace(chr(10), ' ')}  ")
    lines += ["", "### Execution trace (nodes, tool calls, routing, reflection)", "", *_trace(o.runs)]
    lines += ["### Expected outputs", "", *_outputs(o.outputs), "", "---", ""]
    return lines


def render_report(run: ExamRun, *, llm_label: str, trace_path: str | None = None) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    total = sum(len(o.checks) for o in run.outcomes) + len(run.suite_checks)
    passed = sum(c.passed for o in run.outcomes for c in o.checks) + sum(c.passed for c in run.suite_checks)
    lines = [
        "# MindBridge Intake AI — Exam Scenario Execution Report",
        "",
        f"Generated {now} · mode **{run.mode}** · LLM: {llm_label} · "
        f"**{passed}/{total} checks passed** {_tick(run.passed)}",
        "",
        "Each scenario runs end-to-end through the real LangGraph `StateGraph` (SQLite assessment store, "
        "SqliteSaver checkpoints, the 4 assessment tools, deterministic audit engine, reflection loop and "
        "clinician `interrupt()`).",
    ]
    if run.mode == "scripted":
        lines.append(
            "In scripted mode only the language model is replaced by a deterministic script, so results are "
            "reproducible offline. Use `--live` to run the same patient messages against Gemini or Ollama."
        )
    if trace_path:
        lines.append(f"Raw machine-readable trace (one JSON event per line): `{trace_path}`.")
    lines += [
        "",
        "> This system organises self-reported information for a qualified professional. It does not "
        "diagnose or recommend treatment.",
        "",
        "## Summary",
        "",
        "| # | Scenario | Final status | Completion | Urgent | Reflection | [M#] | [I#] | [R#] | Checks |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for o in run.outcomes:
        out, state = o.outputs, o.final_state
        info, review = out["missing_or_inconsistent_info"], out["areas_requiring_professional_review"]
        reflection = (
            "passed" if state["reflection_passed"] else ("n/a" if not state["draft_summary"] else "failed")
        )
        lines.append(
            f"| {o.scenario.number} | {o.scenario.title} | `{state['status']}` | {out['completion_status']['percentage']}% | "
            f"{'**yes**' if state['requires_urgent_escalation'] else 'no'} | {reflection} | "
            f"{sum(e.startswith('[M') for e in info)} | {sum(e.startswith('[I') for e in info)} | "
            f"{sum(e.startswith('[R') for e in review)} | {sum(c.passed for c in o.checks)}/{len(o.checks)} {_tick(o.passed)} |"
        )
    lines += ["", "### Suite-level checks", "", *_checks_table(run.suite_checks), ""]
    lines += [
        f"Clinician queue order (urgent first): {' → '.join(f'`{s}`' for s in run.queue_order)}",
        "",
        "---",
        "",
    ]
    for outcome in run.outcomes:
        lines += _scenario(outcome)
    return "\n".join(lines).rstrip() + "\n"
