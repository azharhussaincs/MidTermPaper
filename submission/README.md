# MindBridge Intake AI · Examination 1 submission

**Development of an Intelligent Mental Health Screening and Initial Assessment Agent Using LangGraph**
Author: Azhar Hussain

MindBridge runs a guided mental health check-in, organises the person's own answers into six domains, flags missing,
contradictory and risk information, writes a checked non-diagnostic summary, and pauses for a qualified clinician to
approve it. It never diagnoses or recommends treatment.

## Deliverables

| # | Required deliverable | Where |
|---|---|---|
| 1 | Complete Python source code (backend and frontend) | `01_source_code/MindBridge/` |
| 2 | `requirements.txt` with verified dependencies | `02_requirements/` |
| 3 | README with installation, configuration and execution | `03_readme/README.md` |
| 4 | System architecture diagram | `04_architecture/system_architecture.png`, `langgraph_flow.png` |
| 5 | Dataset and knowledge base, incl. the 5 synthetic scenarios | `05_dataset_knowledge_base/` |
| 6 | Technical report (5–7 pages) | `06_technical_report/MindBridge_Technical_Report.pdf` (7 pages) |
| 7 | Test cases with sample inputs, expected outputs and actual results | `07_test_cases/test_cases.md` |
| 8 | LangSmith traces or equivalent execution logs | `08_execution_logs/` |

## Quick start

```bash
cd 01_source_code/MindBridge
./start.sh            # Windows: start.bat · needs Python 3.11+ and Node.js 20+
```

The script creates the Python environment, installs dependencies, copies `backend/.env.example` to `backend/.env`,
starts the API and the UI, and prints the URLs. Add a `GEMINI_API_KEY` (or run a local Ollama model) to chat with a real
model. The 5 test scenarios need no key:

```bash
cd 01_source_code/MindBridge/backend && .venv/bin/python -m scripts.run_exam_scenarios
```

## Verification performed for this submission

| Check | Result |
|---|---|
| Fresh install of `01_source_code` in an empty directory (new virtualenv, `pip install -r requirements.txt`, `npm ci`) | Succeeded |
| Backend test suite on the fresh install | 113 passed, 2 skipped (opt-in live-model tests) |
| 5 required scenarios, scripted model | 34/34 checks passed |
| Live Google Gemini, current code | Scenario 3 only: 6/6 checks passed; invented self-care values were rejected until the patient answered. A full 5-scenario live rerun was stopped by the free-tier rate limit and is not verified |
| Live Google Gemini, before the grounding fix | All 5 scenarios: 33/34 (scenario 3 escalated on a self-care answer the patient never gave) |
| Browser checks at 375px and 1440px | 16/16 passed: crisis contacts visible on opening a safety pause, pause/resume, evidence navigation |
| Frontend production build (`tsc -b && vite build`) | Succeeded |
| Pinned Python versions vs. the tested environment | 19/19 match; `pip check` clean |
| Secret scan of the whole submission folder | No API keys; only `.env.example` placeholders |

## Requirement coverage

| Exam requirement | Implementation |
|---|---|
| LangChain LLM integration and tool calling | Gemini / Ollama chat models with `bind_tools` (`backend/app/core/llm_manager.py`, `graph/nodes.py`) |
| LangGraph StateGraph and state schema | `StateGraph(AssessmentGraphState)`, 8 nodes (`graph/workflow.py`, `graph/state.py`) |
| At least two functional tools | 4: store, retrieve, validate/audit, questionnaire guide (`tools/assessment_tools.py`) |
| Conditional edges | 4 routers: already reviewed, tool calls, urgent, pause, complete or sent early, reflection retry |
| Memory / checkpointing | `SqliteSaver`, one thread per session; resume after restart is tested |
| Reflection / validation of the summary | `reflect_summary`: rule checks + LLM reviewer; a failed summary is regenerated once |
| Human-in-the-loop | `interrupt()` in `clinician_review_gate`; the clinician's decision resumes it with `Command(resume=…)` |
| Missing / inconsistent information | 18 required fields, 7 contradiction rules, changed-answer detection |
| Structured summary with the 5 expected outputs | `AssessmentSummaryOutput` |
| Execution logs | JSONL trace per graph step; LangSmith when a key is configured |
| 5 synthetic test scenarios | Complete, missing, conflicting, significant distress, interrupted |
