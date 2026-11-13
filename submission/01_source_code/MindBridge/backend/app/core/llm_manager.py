"""Hybrid LLM manager: local Ollama bootstrap + unified LangChain chat-model factory.

Providers:
    local   -> ChatOllama (Ollama is installed, started and the model pulled on demand)
    gemini  -> ChatGoogleGenerativeAI
    auto    -> local if it becomes ready within OLLAMA_AUTO_FALLBACK_TIMEOUT, else Gemini.
               Local setup keeps running in the background, so later calls switch to local.

Verify from the backend directory:
    python -m app.core.llm_manager --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

if __package__ in (None, ""):  # allow `python app/core/llm_manager.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import LLMProvider, Settings, get_settings

logger = logging.getLogger(__name__)

OLLAMA_INSTALL_SCRIPT_URL = "https://ollama.com/install.sh"
ActiveProvider = Literal["local", "gemini"]

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_PERCENT = re.compile(r"(\d{1,3})%")
_SETUP_RETRY_COOLDOWN = 60.0

_COMMON_BINARY_PATHS: dict[str, list[str]] = {
    "Linux": ["/usr/local/bin/ollama", "/usr/bin/ollama"],
    "Darwin": [
        "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama",
        "/Applications/Ollama.app/Contents/Resources/ollama",
    ],
    "Windows": [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")],
}

_WINDOWS_INSTRUCTIONS = (
    "Automatic Ollama install on Windows needs winget, which was not found. Install manually:\n"
    "  1. Download https://ollama.com/download/OllamaSetup.exe and run it, or\n"
    "  2. In PowerShell: irm https://ollama.com/install.ps1 | iex\n"
    "Then restart the backend, or set LLM_PROVIDER=gemini to skip local inference."
)


class OllamaSetupError(RuntimeError):
    """Local Ollama could not be installed, started or provisioned."""


class LLMUnavailableError(RuntimeError):
    """No configured provider could produce a chat model."""


@dataclass(slots=True)
class OllamaReadiness:
    binary_path: str
    base_url: str
    model: str
    installed_now: bool = False
    started_server: bool = False
    pulled_model: bool = False
    supports_tools: bool = False


@dataclass(slots=True)
class _SetupJob:
    future: Future[OllamaReadiness]
    started_at: float


_state_lock = threading.Lock()
_server_process: subprocess.Popen[bytes] | None = None
_setup_jobs: dict[tuple[str, str], _SetupJob] = {}
# Runtime overrides set from the API (e.g. switching provider from the UI) without a restart.
_runtime_overrides: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


class _ProgressLogger:
    """Collapses carriage-return progress bars into one log line per 10% step."""

    def __init__(self, label: str) -> None:
        self._label = label
        self._last_line = ""
        self._last_bucket: dict[str, int] = {}

    def __call__(self, line: str) -> None:
        match = _PERCENT.search(line)
        if match is None:
            if line != self._last_line:
                logger.info("[%s] %s", self._label, line)
            self._last_line = line
            return
        phase = line[: match.start()].strip()
        bucket = int(match.group(1)) // 10
        if self._last_bucket.get(phase) != bucket:
            self._last_bucket[phase] = bucket
            logger.info("[%s] %s", self._label, line)


def _run_streaming(
    cmd: list[str],
    *,
    timeout: float,
    label: str,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Run a command, streaming cleaned output lines; raise OllamaSetupError on failure."""
    emit = on_line or (lambda line: logger.info("[%s] %s", label, line))
    tail: deque[str] = deque(maxlen=15)
    logger.info("[%s] running: %s", label, " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
    except OSError as exc:
        raise OllamaSetupError(f"{label}: could not start {cmd[0]!r}: {exc}") from exc

    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        proc.kill()

    watchdog = threading.Timer(timeout, _kill)
    watchdog.daemon = True
    watchdog.start()

    def _handle(raw: bytes) -> None:
        line = _ANSI_ESCAPE.sub("", raw.decode("utf-8", errors="replace")).strip()
        if line:
            tail.append(line)
            emit(line)

    try:
        assert proc.stdout is not None
        buffer = b""
        while chunk := proc.stdout.read1(4096):
            buffer += chunk
            *lines, buffer = re.split(rb"[\r\n]", buffer)
            for raw in lines:
                _handle(raw)
        _handle(buffer)
        returncode = proc.wait()
    finally:
        watchdog.cancel()

    if timed_out.is_set():
        raise OllamaSetupError(f"{label}: timed out after {timeout:.0f}s")
    if returncode != 0:
        details = "\n  ".join(tail) or "(no output)"
        raise OllamaSetupError(f"{label}: exited with code {returncode}:\n  {details}")


# ---------------------------------------------------------------------------
# a. Binary
# ---------------------------------------------------------------------------


def find_ollama_binary() -> str | None:
    if found := shutil.which("ollama"):
        return found
    for candidate in _COMMON_BINARY_PATHS.get(platform.system(), []):
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def install_ollama(timeout: float) -> str:
    """Install Ollama with the platform's official non-interactive method."""
    system = platform.system()
    logger.warning("Ollama CLI not found; attempting automatic install (os=%s)", system)

    if system == "Windows":
        if not shutil.which("winget"):
            raise OllamaSetupError(_WINDOWS_INSTRUCTIONS)
        cmd = [
            "winget", "install", "--id", "Ollama.Ollama", "-e", "--silent",
            "--accept-package-agreements", "--accept-source-agreements",
        ]  # fmt: skip
    elif system == "Darwin" and shutil.which("brew"):
        cmd = ["brew", "install", "ollama"]
    elif system in ("Linux", "Darwin"):
        if not shutil.which("curl"):
            raise OllamaSetupError("curl is required to install Ollama automatically")
        cmd = ["sh", "-c", f"curl -fsSL {OLLAMA_INSTALL_SCRIPT_URL} | sh"]
    else:
        raise OllamaSetupError(f"Unsupported OS {system!r}; install Ollama from https://ollama.com")

    try:
        _run_streaming(cmd, timeout=timeout, label="ollama-install")
    except OllamaSetupError as exc:
        # The Linux script needs root; without a TTY sudo cannot prompt for a password.
        raise OllamaSetupError(
            f"{exc}\nInstall manually with: curl -fsSL {OLLAMA_INSTALL_SCRIPT_URL} | sh"
        ) from exc

    binary = find_ollama_binary()
    if binary is None:
        raise OllamaSetupError("Installer finished but the `ollama` binary is not on PATH")
    logger.info("Ollama installed at %s", binary)
    return binary


# ---------------------------------------------------------------------------
# b. Service
# ---------------------------------------------------------------------------


def is_ollama_running(base_url: str, timeout: float = 2.0) -> bool:
    try:
        httpx.get(f"{base_url}/api/tags", timeout=timeout).raise_for_status()
    except httpx.HTTPError:
        return False
    return True


def start_ollama_server(binary: str, base_url: str, timeout: float) -> None:
    """Spawn `ollama serve` detached and poll /api/tags until it answers."""
    global _server_process

    parsed = urlparse(base_url)
    if parsed.hostname not in _LOCAL_HOSTS:
        raise OllamaSetupError(f"Ollama at {base_url} is unreachable and is not local; cannot start it")

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"{parsed.hostname}:{parsed.port or 11434}"
    kwargs: dict[str, Any] = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        kwargs["start_new_session"] = True

    logger.info("Ollama server not responding at %s; starting `ollama serve`", base_url)
    proc = subprocess.Popen(
        [binary, "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        **kwargs,
    )
    _server_process = proc

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_ollama_running(base_url, timeout=1.0):
            logger.info("Ollama server is up (pid=%s)", proc.pid)
            return
        if proc.poll() is not None:
            # Another instance may have bound the port in the meantime.
            if is_ollama_running(base_url, timeout=1.0):
                return
            raise OllamaSetupError(f"`ollama serve` exited early with code {proc.returncode}")
        time.sleep(0.5)
    raise OllamaSetupError(f"Ollama server did not respond within {timeout:.0f}s")


def shutdown_ollama_server() -> None:
    """Stop the server only if this process started it."""
    global _server_process
    if _server_process is not None and _server_process.poll() is None:
        logger.info("Stopping Ollama server (pid=%s)", _server_process.pid)
        _server_process.terminate()
        try:
            _server_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _server_process.kill()
    _server_process = None


# ---------------------------------------------------------------------------
# c. Model
# ---------------------------------------------------------------------------


def list_local_models(base_url: str, timeout: float = 5.0) -> list[str]:
    response = httpx.get(f"{base_url}/api/tags", timeout=timeout)
    response.raise_for_status()
    return [
        name
        for entry in response.json().get("models", [])
        if (name := entry.get("name") or entry.get("model"))
    ]


def is_model_available(model: str, available: list[str]) -> bool:
    """`llama3.2` and `llama3.2:latest` refer to the same model."""
    wanted = model if ":" in model else f"{model}:latest"
    return wanted in available or model in available


def pull_model(binary: str, model: str, timeout: float) -> None:
    logger.info("Model %r not found locally; pulling (this can take several minutes)", model)
    _run_streaming(
        [binary, "pull", model],
        timeout=timeout,
        label=f"ollama-pull {model}",
        on_line=_ProgressLogger(f"ollama-pull {model}"),
    )


def load_model(base_url: str, model: str, timeout: float) -> bool:
    """Load the model into memory (empty prompt) to prove the server can actually run it.

    A listed model is not enough: a broken install answers /api/tags but fails here.
    Returns whether the model advertises the `tools` capability needed for bind_tools().
    """
    logger.info("Loading %r into Ollama to verify inference", model)
    try:
        httpx.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": "10m", "stream": False},
            timeout=timeout,
        ).raise_for_status()
        show = httpx.post(f"{base_url}/api/show", json={"model": model}, timeout=10.0)
        show.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise OllamaSetupError(f"Ollama cannot run {model!r}: {exc.response.text.strip()}") from exc
    except httpx.HTTPError as exc:
        raise OllamaSetupError(f"Ollama did not load {model!r} within {timeout:.0f}s: {exc}") from exc

    supports_tools = "tools" in show.json().get("capabilities", [])
    if not supports_tools:
        logger.warning("Model %r does not support tool calling; bind_tools() will fail", model)
    return supports_tools


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def ensure_ollama_ready(
    model_name: str | None = None,
    *,
    settings: Settings | None = None,
    auto_install: bool | None = None,
    auto_pull: bool | None = None,
) -> OllamaReadiness:
    """Binary -> service -> model -> inference. Blocking; raises OllamaSetupError on any failure."""
    settings = settings or get_effective_settings()
    model = model_name or settings.default_local_model
    base_url = settings.ollama_base_url
    auto_install = settings.ollama_auto_install if auto_install is None else auto_install
    auto_pull = settings.ollama_auto_pull if auto_pull is None else auto_pull
    remote = urlparse(base_url).hostname not in _LOCAL_HOSTS

    binary = find_ollama_binary()
    installed_now = started = pulled = False

    # a. Binary (not needed for a remote server that already answers)
    if binary is None and not (remote and is_ollama_running(base_url)):
        if not auto_install:
            raise OllamaSetupError("Ollama is not installed and OLLAMA_AUTO_INSTALL is disabled")
        binary = install_ollama(settings.ollama_install_timeout)
        installed_now = True
    logger.debug("Ollama binary: %s", binary or "(remote)")

    # b. Service
    if not is_ollama_running(base_url):
        assert binary is not None
        start_ollama_server(binary, base_url, settings.ollama_startup_timeout)
        started = True

    # c. Model
    try:
        available = list_local_models(base_url)
    except httpx.HTTPError as exc:
        raise OllamaSetupError(f"Could not list Ollama models at {base_url}: {exc}") from exc
    if not is_model_available(model, available):
        if not auto_pull:
            raise OllamaSetupError(
                f"Model {model!r} is not pulled and OLLAMA_AUTO_PULL is disabled; run `ollama pull {model}`"
            )
        if binary is None:
            raise OllamaSetupError(f"Model {model!r} is missing on remote Ollama {base_url}")
        pull_model(binary, model, settings.ollama_pull_timeout)
        if not is_model_available(model, list_local_models(base_url)):
            raise OllamaSetupError(f"`ollama pull {model}` finished but the model is not listed")
        pulled = True

    # d. Inference
    supports_tools = load_model(base_url, model, settings.ollama_load_timeout)

    readiness = OllamaReadiness(binary or "", base_url, model, installed_now, started, pulled, supports_tools)
    logger.info("Ollama ready: %s", asdict(readiness))
    return readiness


async def aensure_ollama_ready(model_name: str | None = None, **kwargs: Any) -> OllamaReadiness:
    return await asyncio.to_thread(ensure_ollama_ready, model_name, **kwargs)


def warm_up_local_llm(
    model_name: str | None = None, *, settings: Settings | None = None, force: bool = False
) -> Future[OllamaReadiness]:
    """Start (or join) background local setup; at most one job per (base_url, model).

    Runs on a daemon thread so a long model pull never blocks interpreter shutdown.
    A failed job is retried only after a cooldown so callers don't hammer the installer.
    """
    settings = settings or get_effective_settings()
    model = model_name or settings.default_local_model
    key = (settings.ollama_base_url, model)

    with _state_lock:
        job = _setup_jobs.get(key)
        if job is not None and not (force and job.future.done()):
            failed = job.future.done() and job.future.exception() is not None
            if not failed or time.monotonic() - job.started_at < _SETUP_RETRY_COOLDOWN:
                return job.future

        future: Future[OllamaReadiness] = Future()
        future.set_running_or_notify_cancel()

        def _run() -> None:
            try:
                future.set_result(ensure_ollama_ready(model, settings=settings))
            except BaseException as exc:  # surface everything through the future
                logger.error("Local LLM setup failed: %s", exc)
                future.set_exception(exc)

        threading.Thread(target=_run, name=f"ollama-setup:{model}", daemon=True).start()
        _setup_jobs[key] = _SetupJob(future, time.monotonic())
        return future


def _local_ready_now(settings: Settings, model: str) -> bool:
    try:
        return is_model_available(model, list_local_models(settings.ollama_base_url, timeout=1.5))
    except httpx.HTTPError:
        return False


def _wait_for_local(settings: Settings, model: str, timeout: float | None) -> None:
    future = warm_up_local_llm(model, settings=settings)
    if future.done() and future.exception() is None and not _local_ready_now(settings, model):
        # Verified earlier, but the server or model has gone away since: re-run setup.
        future = warm_up_local_llm(model, settings=settings, force=True)
    future.result(timeout=timeout)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _build_ollama(settings: Settings, model: str, temperature: float) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, base_url=settings.ollama_base_url, temperature=temperature)


def _build_gemini(settings: Settings, temperature: float) -> BaseChatModel:
    if settings.gemini_api_key is None:
        raise LLMUnavailableError("GEMINI_API_KEY is not set (or is still the .env.example placeholder)")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
        timeout=settings.gemini_timeout,
        max_retries=settings.gemini_max_retries,
    )


def get_llm(
    provider: str | None = None,
    temperature: float | None = None,
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> BaseChatModel:
    """Return a tool-calling capable chat model for `provider` (default: LLM_PROVIDER)."""
    settings = settings or get_effective_settings()
    resolved = _normalise_provider(provider or settings.llm_provider)
    temperature = settings.llm_temperature if temperature is None else temperature
    local_model = model or settings.default_local_model

    if resolved == "gemini":
        llm = _build_gemini(settings, temperature)
    elif resolved == "local":
        _wait_for_local(settings, local_model, timeout=None)
        llm = _build_ollama(settings, local_model, temperature)
    else:
        try:
            _wait_for_local(settings, local_model, timeout=settings.ollama_auto_fallback_timeout)
            llm = _build_ollama(settings, local_model, temperature)
            resolved = "local"
        except Exception as exc:
            reason = (
                f"setup still in progress after {settings.ollama_auto_fallback_timeout:.0f}s"
                if isinstance(exc, TimeoutError)
                else str(exc)
            )
            if not settings.gemini_configured:
                raise LLMUnavailableError(
                    f"Local Ollama unavailable ({reason}) and GEMINI_API_KEY is not configured"
                ) from exc
            logger.warning("Local Ollama unavailable (%s); falling back to Gemini", reason)
            llm = _build_gemini(settings, temperature)
            resolved = "gemini"

    logger.info("LLM ready: provider=%s model=%s", resolved, _model_name(llm))
    return llm


async def aget_llm(
    provider: str | None = None, temperature: float | None = None, **kwargs: Any
) -> BaseChatModel:
    return await asyncio.to_thread(get_llm, provider, temperature, **kwargs)


def get_effective_settings() -> Settings:
    """`.env` settings with any runtime overrides from `configure_llm` applied."""
    with _state_lock:
        overrides = dict(_runtime_overrides)
    base = get_settings()
    return base.model_copy(update=overrides) if overrides else base


def configure_llm(provider: str | None = None, local_model: str | None = None) -> Settings:
    """Change the process-wide default provider and/or local model at runtime."""
    resolved = _normalise_provider(provider) if provider is not None else None
    with _state_lock:
        if resolved is not None:
            _runtime_overrides["llm_provider"] = resolved
        if local_model is not None:
            _runtime_overrides["default_local_model"] = local_model.strip()
    logger.info("LLM runtime configuration updated: %s", _runtime_overrides)
    return get_effective_settings()


def reset_llm_configuration() -> None:
    with _state_lock:
        _runtime_overrides.clear()


def _normalise_provider(provider: str) -> LLMProvider:
    value = provider.strip().lower()
    value = "local" if value == "ollama" else value
    if value not in ("auto", "local", "gemini"):
        raise ValueError(f"Unknown LLM provider {provider!r}; expected auto, local or gemini")
    return value  # type: ignore[return-value]


def _model_name(llm: BaseChatModel) -> str:
    return str(getattr(llm, "model", None) or getattr(llm, "model_name", "unknown"))


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_llm_status(model: str | None = None, *, settings: Settings | None = None) -> dict[str, Any]:
    """Side-effect free, JSON-serialisable engine status for the API and UI."""
    settings = settings or get_effective_settings()
    local_model = model or settings.default_local_model
    base_url = settings.ollama_base_url

    running = is_ollama_running(base_url, timeout=1.5)
    local_available = running and _local_ready_now(settings, local_model)

    setup_state, setup_error = "idle", None
    with _state_lock:
        job = _setup_jobs.get((base_url, local_model))
    if job is not None:
        if not job.future.done():
            setup_state = "in_progress"
        elif (exc := job.future.exception()) is not None:
            setup_state, setup_error = "failed", str(exc)
        else:
            setup_state = "ready"
    local_usable = local_available and setup_state != "failed"

    active: ActiveProvider | None
    if settings.llm_provider == "gemini":
        active = "gemini" if settings.gemini_configured else None
    elif settings.llm_provider == "local":
        active = "local" if local_usable else None
    else:
        active = "local" if local_usable else ("gemini" if settings.gemini_configured else None)

    return {
        "active_provider": active,
        "configured_provider": settings.llm_provider,
        "ollama_installed": find_ollama_binary() is not None,
        "ollama_running": running,
        "local_model_available": local_available,
        "gemini_configured": settings.gemini_configured,
        "local_model": local_model,
        "gemini_model": settings.gemini_model,
        "ollama_base_url": base_url,
        "local_setup": setup_state,
        "local_setup_error": setup_error,
    }


# ---------------------------------------------------------------------------
# Standalone verification
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    from langchain_core.tools import tool

    from app.core.logging_config import setup_logging

    parser = argparse.ArgumentParser(description="Verify the hybrid LLM engine.")
    parser.add_argument("--provider", choices=["auto", "local", "gemini"], help="override LLM_PROVIDER")
    parser.add_argument("--model", help="override DEFAULT_LOCAL_MODEL")
    parser.add_argument("--no-install", action="store_true", help="never auto-install Ollama")
    parser.add_argument("--no-pull", action="store_true", help="never auto-pull the model")
    parser.add_argument("--no-invoke", action="store_true", help="only resolve the model, skip LLM calls")
    args = parser.parse_args(argv)

    settings = get_settings()
    overrides: dict[str, Any] = {}
    if args.no_install:
        overrides["ollama_auto_install"] = False
    if args.no_pull:
        overrides["ollama_auto_pull"] = False
    if args.model:
        overrides["default_local_model"] = args.model
    settings = settings.model_copy(update=overrides)
    setup_logging(settings.log_level)

    print("== Status before ==")
    print(json.dumps(get_llm_status(settings=settings), indent=2))

    try:
        llm = get_llm(args.provider, settings=settings)
    except (LLMUnavailableError, OllamaSetupError, ValueError) as exc:
        logger.error("Could not initialise an LLM: %s", exc)
        print(json.dumps(get_llm_status(settings=settings), indent=2))
        return 1

    print(f"\n== Resolved {type(llm).__name__} ({_model_name(llm)}) ==")

    if not args.no_invoke:

        @tool
        def record_phq_item(item: int, score: int) -> str:
            """Record the 0-3 score a user gave for a PHQ-9 item (1-9)."""
            return f"item {item} = {score}"

        try:
            reply = llm.invoke("Reply with exactly the word: READY")
        except Exception as exc:
            logger.error("Model resolved but invocation failed: %s", exc)
            return 1
        print(f"Plain invoke   -> {reply.content!r}")
        try:
            tool_reply = llm.bind_tools([record_phq_item]).invoke(
                "The user scored PHQ-9 item 2 as 3. Record it with the tool."
            )
            print(f"Tool calling   -> {tool_reply.tool_calls}")
        except Exception as exc:  # e.g. Ollama models without the `tools` capability
            print(f"Tool calling   -> NOT SUPPORTED by {_model_name(llm)}: {exc}")

    print("\n== Status after ==")
    print(json.dumps(get_llm_status(settings=settings), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
