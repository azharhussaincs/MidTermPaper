# 08 · Execution logs (equivalent of LangSmith traces)

LangSmith tracing is built in but needs a personal `LANGCHAIN_API_KEY`, which is not part of this submission. The
evidence here is the project's own execution logging, which records every LangGraph step of every run.

| File | Run | Result |
|---|---|---|
| `exam_execution_report.md` | 5 scenarios, scripted model (deterministic, offline), 2026-11-13 11:05 UTC | 34/34 checks passed |
| `exam_execution_trace.jsonl` | Event-by-event trace of that run | 195 events |
| `exam_execution_report_live_s3.md` | Scenario 3 with Google Gemini (`gemini-flash-lite-latest`) on the current code, 2026-11-13 11:10 UTC | 6/6 checks passed (5 scenario checks + all 5 outputs). The model tried four times to store a self-care value the patient had not given; each was rejected ("Not stored: answer not given by the person") and stored only after the patient answered |
| `exam_execution_trace_live_s3.jsonl` | Event-by-event trace of that run | 82 events |
| `exam_execution_report_live.md` | All 5 scenarios with Gemini, 2026-11-13 10:30 UTC, **before** the grounding fix | 33/34: scenario 3 was escalated because the model stored a self-care answer the patient never gave. A full 5-scenario live rerun on the current code was stopped by the Gemini free-tier limit (15 requests/minute) and is not reported |
| `exam_execution_trace_live.jsonl` | Event-by-event trace of that run | 326 events |

## What a trace records

`backend/app/core/execution_logger.py` writes one JSON object per event:
`ts`, `run_id`, `session_id`, `label`, `step`, `kind`, `node`, `data`.

| `kind` | Meaning | Scripted run | Live run (10:30) |
|---|---|---|---|
| `node` | A graph node finished: tool calls with arguments, completion %, missing count, flags | 81 | 147 |
| `route` | A conditional edge decision: the router used and the next node | 81 | 147 |
| `end` | A graph run ended and what is pending next | 22 | 21 |
| `interrupt` | The run paused at `clinician_review_gate` for a human | 4 | 4 |
| `note` | Events outside the graph, e.g. the greeting seeded without an LLM call | 7 | 7 |

Tool calls in the 10:30 live run: `store_assessment_response` 31, `get_screening_questionnaire_guide` 16,
`validate_and_audit_responses` 4, `retrieve_assessment_record` 1. Each conversation starts with the fixed greeting
exactly once; the model does not greet again or address the person by their code.

Each report renders the same events as readable tables per scenario: the conversation, every node with its tool
calls and results, every routing decision, the reflection verdicts, the clinician interrupt, and the 5 expected outputs.

## Reproducing the logs

```bash
cd backend
.venv/bin/python -m scripts.run_exam_scenarios                       # scripted: logs/exam_execution_report.md + trace
.venv/bin/python -m scripts.run_exam_scenarios --live --provider gemini \
  --report logs/exam_execution_report_live.md --trace logs/exam_execution_trace_live.jsonl   # needs GEMINI_API_KEY
```

While the app runs, every conversation is also traced to `backend/logs/execution_trace.jsonl`.

## Enabling LangSmith

Set these in `backend/.env` and restart the backend; LangChain then sends every model call, tool call and graph
step to the LangSmith project:

```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your LangSmith key>
LANGCHAIN_PROJECT=mental-health-screening-agent
```
