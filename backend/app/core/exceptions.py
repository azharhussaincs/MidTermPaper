"""Domain exceptions and FastAPI exception handlers.

Every error leaves the API in one envelope, so the frontend has a single shape to handle:

    {"error": {"code": "session_not_found", "message": "...", "details": ...}}

Unexpected exceptions are converted by `UnhandledErrorMiddleware`, which sits *inside* the CORS
middleware. FastAPI's own `Exception` handler runs outside CORS, so its 500 responses carry no
CORS headers and the browser reports them as a network failure instead of showing the error.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.llm_manager import LLMUnavailableError, OllamaSetupError

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": jsonable_encoder(details)}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            error_body("validation_error", "The request is invalid.", details),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(
            error_body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(LLMUnavailableError)
    @app.exception_handler(OllamaSetupError)
    async def _llm_error(_: Request, exc: Exception) -> JSONResponse:
        logger.error("LLM unavailable: %s", exc)
        return JSONResponse(
            error_body(
                "llm_unavailable",
                "The language model is not available right now. Check the engine status and try again.",
                str(exc),
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            error_body("internal_error", "Something went wrong on our side. Please try again."),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ---------------------------------------------------------------------------
# Unhandled errors (CORS-safe)
# ---------------------------------------------------------------------------

_PROVIDER_MODULES = (
    "langchain_google_genai",
    "google.genai",
    "google.api_core",
    "langchain_ollama",
    "ollama",
)


def is_llm_provider_error(exc: BaseException) -> bool:
    """Errors raised by the Gemini/Ollama clients (model retired, overloaded, quota, auth…)."""
    return any(
        type(e).__module__.startswith(_PROVIDER_MODULES) for e in (exc, exc.__cause__) if e is not None
    )


def unhandled_error_response(exc: BaseException) -> tuple[int, dict]:
    if is_llm_provider_error(exc):
        detail = " ".join(str(exc).split())[:300]
        return 503, error_body(
            "llm_provider_error",
            "The AI model could not answer right now (it may be busy or misconfigured). Please try again shortly.",
            detail,
        )
    return 500, error_body("internal_error", "Something went wrong on our side. Please try again.")


class UnhandledErrorMiddleware:
    """Turns any uncaught exception into the JSON error envelope, inside the CORS layer."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:  # too late to change the response; let the server log it
                raise
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            status_code, body = unhandled_error_response(exc)
            payload = json.dumps(body).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
