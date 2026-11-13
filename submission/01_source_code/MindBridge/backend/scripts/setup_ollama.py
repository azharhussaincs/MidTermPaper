"""Provision local Ollama without starting the API: `python -m scripts.setup_ollama [--model NAME]`."""

import sys

from app.core.llm_manager import _main

if __name__ == "__main__":
    raise SystemExit(_main(["--provider", "local", "--no-invoke", *sys.argv[1:]]))
