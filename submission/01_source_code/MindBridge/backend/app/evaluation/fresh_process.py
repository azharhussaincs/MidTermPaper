"""Read a session's persisted state from a brand-new Python process.

Used by the interrupted-assessment scenario to prove that state lives in SQLite (assessment
store + LangGraph checkpointer), not in the memory of the process that created it:

    python -m app.evaluation.fresh_process --session-id ID --db DB --checkpoints CKPT
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any


def read_session(session_id: str, db_path: str, checkpoint_path: str) -> dict[str, Any]:
    from app.db.checkpointer import close_checkpointer, create_checkpointer
    from app.db.database import dispose_db, init_db
    from app.graph.workflow import build_graph, get_session_state

    def no_llm(provider: str | None, temperature: float | None) -> Any:
        raise RuntimeError("Reading persisted state must not call an LLM")

    init_db(db_path)
    checkpointer = create_checkpointer(checkpoint_path)
    try:
        state = get_session_state(session_id, graph=build_graph(no_llm, checkpointer))
    finally:
        close_checkpointer(checkpointer)
        dispose_db()
    return {
        "pid": os.getpid(),
        "status": state["status"],
        "completion_pct": state["completion_pct"],
        "message_count": len(state["messages"]),
        "user_messages": [m["content"] for m in state["messages"] if m["role"] == "user"],
        "missing_fields": len(state["missing_fields"]),
        "next_nodes": state["next_nodes"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--checkpoints", required=True)
    args = parser.parse_args()
    print(json.dumps(read_session(args.session_id, args.db, args.checkpoints)))


if __name__ == "__main__":
    main()
