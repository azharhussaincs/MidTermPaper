"""Run the 5 exam scenarios end-to-end and write the evaluation report, or seed the UI.

From the backend directory:

    python -m scripts.run_exam_scenarios                 # scripted (offline, deterministic) report
    python -m scripts.run_exam_scenarios --live          # same patient messages against the real LLM
    python -m scripts.run_exam_scenarios --seed-ui       # put the 5 cases into the dev DB for the React UI

Outputs (report mode): logs/exam_execution_report.md and logs/exam_execution_trace.jsonl.
Exit code is 1 if any check fails (scripted mode, or --strict in live mode).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from app.core.config import BACKEND_DIR, get_settings
from app.core.execution_logger import ExecutionLogger, configure_langsmith, set_execution_logger
from app.core.llm_manager import configure_llm, get_llm_status
from app.core.logging_config import setup_logging
from app.db.database import dispose_db, init_db
from app.evaluation.report import render_report
from app.evaluation.runner import (
    ExamRun,
    live_graph_factory,
    purge_sessions,
    run_exam,
    scripted_graph_factory,
)
from app.evaluation.scenarios import EXAM_SCENARIOS

DEFAULT_REPORT = BACKEND_DIR / "logs" / "exam_execution_report.md"
DEFAULT_TRACE = BACKEND_DIR / "logs" / "exam_execution_trace.jsonl"
SEED_PREFIX = "demo"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 5 synthetic exam scenarios.")
    parser.add_argument(
        "--live", action="store_true", help="use the real LLM (Gemini or Ollama) instead of the script"
    )
    parser.add_argument("--provider", choices=["auto", "local", "gemini"], help="LLM provider for --live")
    parser.add_argument(
        "--seed-ui", action="store_true", help="seed the dev database with the 5 cases for the UI"
    )
    parser.add_argument("--scenarios", help="comma-separated scenario numbers, e.g. 1,4 (default: all)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Markdown report path")
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE, help="JSONL trace path")
    parser.add_argument(
        "--keep-db", action="store_true", help="keep the run's SQLite files in logs/exam_run/"
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 on failed checks in --live mode too")
    return parser.parse_args(argv)


def _llm_label(live: bool) -> str:
    if not live:
        return "deterministic script (offline)"
    status = get_llm_status()
    model = status["local_model"] if status["active_provider"] == "local" else status["gemini_model"]
    return f"{status['active_provider'] or 'none available'} ({model})"


def _print_summary(run: ExamRun) -> None:
    print()
    for outcome in run.outcomes:
        state = outcome.final_state
        passed = sum(c.passed for c in outcome.checks)
        print(
            f"  {'PASS' if outcome.passed else 'FAIL'}  Scenario {outcome.scenario.number}: {outcome.scenario.title:<44} "
            f"{state['status']:<26} {outcome.outputs['completion_status']['percentage']:>5}%  "
            f"checks {passed}/{len(outcome.checks)}"
        )
        for check in outcome.checks:
            if not check.passed:
                print(f"        ✗ {check.name}: {check.detail[:120]}")
    for check in run.suite_checks:
        print(f"  {'PASS' if check.passed else 'FAIL'}  {check.name}")
    print(f"\n  Clinician queue (urgent first): {', '.join(run.queue_order)}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    setup_logging("WARNING")
    configure_langsmith(settings)
    if args.provider:
        configure_llm(args.provider)

    scenarios = EXAM_SCENARIOS
    if args.scenarios:
        wanted = {int(n) for n in args.scenarios.split(",")}
        scenarios = [s for s in EXAM_SCENARIOS if s.number in wanted]
    mode = "live" if args.live else "scripted"

    if args.seed_ui:
        db_path, checkpoint_path = settings.database_path, settings.checkpoint_db_path
        tracer = ExecutionLogger(
            settings.execution_log_path if settings.execution_log_enabled else None, keep_runs=True
        )
    else:
        work_dir = (
            BACKEND_DIR / "logs" / "exam_run" if args.keep_db else Path(tempfile.mkdtemp(prefix="exam_run_"))
        )
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True)
        db_path, checkpoint_path = work_dir / "exam.db", work_dir / "exam_checkpoints.db"
        args.trace.parent.mkdir(parents=True, exist_ok=True)
        args.trace.unlink(missing_ok=True)
        tracer = ExecutionLogger(args.trace, keep_runs=True)
    set_execution_logger(tracer)

    print(f"Running {len(scenarios)} scenario(s) in {mode} mode · LLM: {_llm_label(args.live)}")
    init_db(db_path)
    try:
        if args.seed_ui:
            ids = [f"{SEED_PREFIX}-s{s.number}-{s.key}" for s in scenarios]
            removed = purge_sessions(ids, checkpoint_path)
            print(f"Seeding the dev database ({db_path}); replaced {removed} previous demo session(s).")
        factory = (live_graph_factory if args.live else scripted_graph_factory)(checkpoint_path)
        run = run_exam(
            mode=mode,
            graph_factory=factory,
            db_path=db_path,
            checkpoint_path=checkpoint_path,
            session_prefix=SEED_PREFIX if args.seed_ui else "exam",
            scenarios=scenarios,
            llm_provider=args.provider,
            resume_interrupted=not args.seed_ui,  # leave scenario 5 paused so it can be resumed live in the UI
        )
    finally:
        dispose_db()
        set_execution_logger(None)

    _print_summary(run)
    if args.seed_ui:
        print(
            "\nSeeded. Start the backend and frontend, then open the Patient Intake and Clinician Review tabs."
        )
        return 0

    args.report.parent.mkdir(parents=True, exist_ok=True)
    trace_label = (
        str(args.trace.relative_to(BACKEND_DIR))
        if args.trace.is_relative_to(BACKEND_DIR)
        else str(args.trace)
    )
    args.report.write_text(
        render_report(run, llm_label=_llm_label(args.live), trace_path=trace_label), encoding="utf-8"
    )
    print(f"\nReport: {args.report}\nTrace:  {args.trace}")
    if not args.keep_db:
        shutil.rmtree(db_path.parent, ignore_errors=True)
    failed = not run.passed and (mode == "scripted" or args.strict)
    return 1 if failed else 0


if __name__ == "__main__":
    logging.captureWarnings(True)
    sys.exit(main())
