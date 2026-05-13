"""Application error types and the FastAPI handler that renders them.

Centralising errors here keeps route handlers free of HTTP plumbing:
they raise a domain exception and the handler maps it to a response.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.schemas import ErrorResponse

logger = logging.getLogger("interview_generator")


class AppError(Exception):
    """Base class for expected, user-visible application errors."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class ConfigurationError(AppError):
    status_code = 500
    code = "configuration_error"
    message = "The server is not configured correctly."


class UpstreamError(AppError):
    """The AI provider failed or returned an unusable response."""

    status_code = 502
    code = "upstream_error"
    message = "The AI provider could not generate a response."


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(code=code, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error: %s (%s)", exc.message, exc.code)
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("validation_error: %s", jsonable_encoder(exc.errors()))
        first = exc.errors()[0] if exc.errors() else {}
        message = first.get("msg", "Invalid request payload.")
        return _error_response(422, "validation_error", message)

    @app.exception_handler(RateLimitExceeded)
    async def _handle_rate_limit(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        logger.warning("rate_limit_exceeded: %s", exc.detail)
        return _error_response(429, "rate_limited", "Too many requests. Please try again later.")

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error: %s", exc)
        return _error_response(500, "internal_error", "An unexpected error occurred.")
