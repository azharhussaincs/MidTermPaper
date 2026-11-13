"""Run the 5 required scenarios through the real LangGraph agent and record inputs, expected and actual results.

Run from the project's backend directory:

    cd backend && PYTHONPATH=. .venv/bin/python ../submission/07_test_cases/generate_test_cases.py

Writes test_cases.json (machine-readable) and test_cases.md (readable) next to this script. Uses the same
runner as `scripts/run_exam_scenarios.py` in scripted mode: only the language model is a deterministic script;
the StateGraph, tools, SQLite store, checkpointer, audit engine, reflection and clinician interrupt are real.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.execution_logger import ExecutionLogger, set_execution_logger
from app.db.database import dispose_db, init_db
from app.evaluation.runner import run_exam, scripted_graph_factory

OUT = Path(__file__).resolve().parent


def _patient_messages(outcome: Any) -> list[str]:
    return [t.user for t in outcome.scenario.all_turns]


def _summarise_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    missing = outputs["missing_or_inconsistent_info"] or []
    review = outputs["areas_requiring_professional_review"] or []
    return {
        "source": outputs["source"],
        "structured_assessment_domains": sorted(outputs["structured_assessment"] or {}),
        "reported_concerns_summary": outputs["reported_concerns_summary"],
        "missing_items": [m for m in missing if m.startswith("[M")],
        "inconsistent_items": [m for m in missing if m.startswith("[I")],
        "areas_requiring_professional_review": review,
        "completion_status": outputs["completion_status"],
        "non_diagnostic_disclaimer_present": bool(outputs.get("non_diagnostic_disclaimer")),
    }


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="mindbridge_test_cases_"))
    db_path, checkpoint_path = work / "exam.db", work / "exam_checkpoints.db"
    set_execution_logger(ExecutionLogger(work / "trace.jsonl", keep_runs=True))
    init_db(db_path)
    try:
        run = run_exam(
            mode="scripted",
            graph_factory=scripted_graph_factory(checkpoint_path),
            db_path=db_path,
            checkpoint_path=checkpoint_path,
            session_prefix="testcase",
        )
    finally:
        dispose_db()
        set_execution_logger(None)
        shutil.rmtree(work, ignore_errors=True)

    cases = []
    for o in run.outcomes:
        cases.append(
            {
                "id": f"TC-{o.scenario.number}",
                "scenario": o.scenario.title,
                "exam_requirement": o.scenario.requirement,
                "sample_input": {
                    "patient_alias": o.scenario.alias,
                    "patient_messages": _patient_messages(o),
                    "submitted_early": o.scenario.finalize_early,
                    "clinician_decision": o.scenario.clinician_review,
                },
                "expected_and_actual": [
                    {"expected": c.name, "actual": c.detail, "result": "PASS" if c.passed else "FAIL"} for c in o.checks
                ],
                "actual_outputs": _summarise_outputs(o.outputs),
                "final_status": o.final_state["status"],
                "result": "PASS" if o.passed else "FAIL",
            }
        )
    suite = [{"expected": c.name, "actual": c.detail, "result": "PASS" if c.passed else "FAIL"} for c in run.suite_checks]
    total = sum(len(o.checks) for o in run.outcomes) + len(run.suite_checks)
    passed = sum(c.passed for o in run.outcomes for c in o.checks) + sum(c.passed for c in run.suite_checks)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    (OUT / "test_cases.json").write_text(
        json.dumps({"generated": generated, "mode": "scripted", "checks_passed": passed, "checks_total": total,
                    "test_cases": cases, "suite_checks": suite}, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )  # fmt: skip

    lines = [
        "# MindBridge · test cases (5 required scenarios)",
        "",
        f"Generated {generated} by `generate_test_cases.py` from a real run of the LangGraph agent (scripted model). "
        f"**{passed}/{total} checks passed.**",
        "",
        "| ID | Scenario | Final status | Checks | Result |",
        "|---|---|---|---|---|",
    ]
    for c in cases:
        ok = sum(r["result"] == "PASS" for r in c["expected_and_actual"])
        lines.append(f"| {c['id']} | {c['scenario']} | `{c['final_status']}` | {ok}/{len(c['expected_and_actual'])} | {c['result']} |")
    for c in cases:
        out = c["actual_outputs"]
        lines += ["", f"## {c['id']} · {c['scenario']}", "", f"**Requirement:** {c['exam_requirement']}", "", "**Sample input (patient messages):**", ""]
        lines += [f"{i}. {m}" for i, m in enumerate(c["sample_input"]["patient_messages"], 1)]
        if c["sample_input"]["submitted_early"]:
            lines += ["", "The patient then submits early (`POST /api/assessments/{id}/finalize`)."]
        if c["sample_input"]["clinician_decision"]:
            lines += ["", f"Clinician decision applied at the review gate: `{json.dumps(c['sample_input']['clinician_decision'])}`"]
        lines += ["", "**Expected vs actual:**", "", "| Expected behaviour | Actual (observed) | Result |", "|---|---|---|"]
        for r in c["expected_and_actual"]:
            actual = str(r["actual"]).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r['expected']} | {actual[:160]}{'…' if len(actual) > 160 else ''} | {r['result']} |")
        cs = out["completion_status"]
        lines += [
            "",
            "**Actual outputs (the 5 expected outputs):**",
            "",
            f"- Structured assessment: domains with answers: {', '.join(out['structured_assessment_domains']) or 'none'}",
            f"- Summary of reported concerns: {out['reported_concerns_summary'] or '(no summary yet: session not submitted)'}",
            f"- Missing / inconsistent: {len(out['missing_items'])} missing, {len(out['inconsistent_items'])} inconsistent"
            + (f" — e.g. {out['inconsistent_items'][0]}" if out["inconsistent_items"] else ""),
            f"- Areas requiring professional review: {len(out['areas_requiring_professional_review'])}"
            + (f" — e.g. {out['areas_requiring_professional_review'][0]}" if out["areas_requiring_professional_review"] else ""),
            f"- Completion status: {cs['percentage']}% · `{cs['status']}`",
        ]
    lines += ["", "## Suite-level checks", "", "| Expected behaviour | Actual | Result |", "|---|---|---|"]
    lines += [f"| {s['expected']} | {str(s['actual']).replace('|', '/')} | {s['result']} |" for s in suite]
    (OUT / "test_cases.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{total} checks passed · wrote test_cases.json and test_cases.md")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
