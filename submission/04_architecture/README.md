# 04 · System architecture diagrams

| File | What it shows |
|---|---|
| `system_architecture.png` / `.svg` | The whole system: React frontend → FastAPI → LangGraph `StateGraph` (state schema and all 8 nodes) → LangChain chat model (`bind_tools`), hybrid LLM manager (Gemini / Ollama), the 4 tools, SQLite assessment DB, `SqliteSaver` checkpoints, execution logging, and the human-in-the-loop path (`interrupt()` → clinician decision → `Command(resume=…)`). |
| `langgraph_flow.png` / `.svg` | The compiled graph in detail: every node, every conditional edge with its condition (`route_after_load`, `route_after_interviewer`, `route_after_tools`, `route_after_reflection`) and every `END`. |
| `architecture_overview.mmd`, `langgraph_state_graph.mmd` | The same two views as Mermaid source, as embedded in the project README. |

Both diagrams were checked against the code: node and router names come from `backend/app/graph/workflow.py`
and `backend/app/graph/nodes.py`; `MAX_REFLECTION_ATTEMPTS = 2` means a failed summary is regenerated once;
the tool names come from `backend/app/tools/assessment_tools.py`.
