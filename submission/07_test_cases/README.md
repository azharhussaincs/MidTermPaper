# 07 · Test cases with sample inputs, expected outputs and actual results

| File | Contents |
|---|---|
| `test_cases.md` | The 5 required scenarios: sample input (the patient's messages), each expected behaviour next to the observed result, and the 5 expected outputs the agent actually produced |
| `test_cases.json` | The same data, machine-readable |
| `generate_test_cases.py` | Regenerates both files from a real run (see the command at the top of the script) |
| `pytest_results.txt` | Full `pytest -v` output of the backend test suite: 113 passed, 2 skipped |
| `fresh_install_verification.txt` | Install, tests, scenarios and frontend build run on a clean copy of `01_source_code` |
| `ui_checks/` | Browser checks of the running app at 375px and 1440px (`ui_checks.py`, `ui_checks_results.txt`: 16/16 passed, `screenshots/`): crisis contacts visible on opening a safety-paused check-in without scrolling, one crisis banner only, pause and resume, evidence navigation to the source message |
| `live_safety_journey.md` | A live check-in with Google Gemini through the running API: the safety question, the reply "Sometimes", escalation, and the state after refresh, as seen by the patient and the clinician |

## The 5 required scenarios

| ID | Exam requirement | Result |
|---|---|---|
| TC-1 | A complete assessment | 8/8 checks pass; approved by the clinician, status `reviewed` |
| TC-2 | An assessment with missing responses | 5/5; submitted early at 50%, all 9 missing fields listed |
| TC-3 | Conflicting responses | 5/5; 3 contradictions surfaced for verification |
| TC-4 | Responses indicating significant distress | 7/7; escalated before the language model ran, first in the clinician queue |
| TC-5 | An incomplete or interrupted assessment | 7/7; paused, read back by a separate process, then resumed on the same session |

## How the tests run

The scenario runner drives the real `StateGraph`, the 4 tools, the SQLite store, the `SqliteSaver` checkpointer, the
audit engine, the reflection step and the clinician `interrupt()`. Only the language model is replaced by a
deterministic script, so the results are reproducible offline and need no API key.

The same patient messages can be replayed against a real model:

```bash
cd backend && .venv/bin/python -m scripts.run_exam_scenarios --live --provider gemini
```

Live Gemini (`gemini-flash-lite-latest`) results are reported separately from the scripted ones. Before the grounding fix, all 5 scenarios passed 33/34: in scenario 3 the model stored a self-care answer the patient never gave, which with severe work impact triggered the extreme-impairment rule. The tool node now rejects energy and self-care values unless the patient talked about them or was asked; scenario 3 now asks for them. On the current code, live scenario 3 passed 6/6 (the model's invented self-care value was rejected four times and stored only after the patient answered). A full 5-scenario live rerun was stopped by the Gemini free-tier limit and is not verified. Reports and traces are in `08_execution_logs/`. Live results vary between runs because the model is not deterministic.

## Backend test suite (`backend/tests`)

| Module | Covers |
|---|---|
| `test_tools.py` | The 4 tools, the audit engine (missing, contradictions, overwritten answers, distress), crisis-language denials, database upgrade |
| `test_graph.py` | Multi-turn memory across restarts, session-id injection, escalation, reflection loop, clinician interrupt, pause and resume |
| `test_api.py` | Every REST endpoint, error envelopes, CORS, queue priority, clinician review, and regression tests from a real session: no repeated greeting, consistent progress after partial submission, pause and resume without losing answers, state that stays identical across refresh and app restart, no duplicate messages when a failed turn is retried, answers to the self-harm question ("Sometimes" and "Not sure" escalate even if the model stores nothing; an explicit "no" continues; "I'd rather not say" continues and leaves the question listed as unanswered), crisis text that leads with location-neutral help, real-name aliases rejected, an option label given to an open clarification is not saved as a description, every progress figure (percentage, questions, topics, summary, list) agrees after a safety pause, and energy or self-care values the patient never mentioned are rejected instead of stored |
| `test_exam_scenarios.py` | The 5 scenarios end to end, the JSONL trace, the Markdown report, UI seeding |

The 2 skipped tests call a live model: they run only with `RUN_LIVE_LLM_TESTS=1` (and, for the Gemini test, a `GEMINI_API_KEY`).
`test_scoring.py` and `test_health.py` are empty placeholders; scoring and the health endpoint are covered in `test_tools.py` and `test_api.py`.
