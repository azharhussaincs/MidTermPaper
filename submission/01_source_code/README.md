# 01 · Complete source code

`MindBridge/` is the full project: Python backend (FastAPI + LangChain + LangGraph), React frontend, tests,
scenario runner and the one-command start/stop scripts. 116 files: 43 Python modules in `backend/app`
(~5,800 lines), 29 TypeScript/TSX files in `frontend/src`.

Excluded on purpose: `backend/.env` (secrets), `backend/.venv` and `frontend/node_modules` (installed on setup),
`frontend/dist` (build output), SQLite databases and the local development trace log. The copy was made from
the project's own file list (`git ls-files --cached --others --exclude-standard`), so it matches what the
`.gitignore` files keep out.

| Path | Contents |
|---|---|
| `backend/app/graph/` | `state.py` (state schema), `nodes.py` (8 nodes + 4 routers), `workflow.py` (StateGraph, checkpointer, session API), `prompts.py` |
| `backend/app/tools/assessment_tools.py` | The 4 LangChain tools |
| `backend/app/services/assessment_audit.py` | Missing-field, contradiction, changed-answer and risk rules |
| `backend/app/core/` | Settings, hybrid LLM manager (Gemini / Ollama), execution logger, LangSmith setup |
| `backend/app/db/` | SQLAlchemy models, repository, SqliteSaver checkpointer |
| `backend/app/schemas/` | Pydantic models for the 6 domains, the summary and the API |
| `backend/app/questionnaires/guides.py` | PHQ-2 / GAD-2 / WHO-5 style question guides |
| `backend/app/evaluation/`, `backend/scripts/` | The 5 scenarios, scripted model, runner, report |
| `backend/tests/` | pytest suite |
| `frontend/src/` | React UI (see `frontend/README.md`) |

Install and run: see `MindBridge/README.md` (also in `03_readme`). Quick start: `./start.sh` (Linux/macOS) or
`start.bat` (Windows), with Python 3.11+ and Node.js 20+.
