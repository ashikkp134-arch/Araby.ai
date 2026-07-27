"""Global exception handlers and request middleware."""

import logging
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log inbound HTTP requests at INFO level."""

    async def dispatch(self, request: Request, call_next: Callable):
        """Process a request and log method/path/status.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/handler.

        Returns:
            Downstream response.
        """
        response = await call_next(request)
        logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app.

    Args:
        app: FastAPI application instance.
    """

    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        """Convert AppException into a standard API response.

        Args:
            _: Unused request.
            exc: Raised application exception.

        Returns:
            JSONResponse with standard envelope.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.message,
                "data": None,
                "error": {
                    "code": exc.error_code,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Convert request validation errors into a standard response.

        Args:
            _: Unused request.
            exc: Raised validation exception.

        Returns:
            JSONResponse with validation details.
        """
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "Validation failed",
                "data": None,
                "error": {
                    "code": "validation_error",
                    "details": exc.errors(),
                },
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        """Hide unexpected internal errors from clients.

        Args:
            _: Unused request.
            exc: Unexpected exception.

        Returns:
            Generic 500 JSONResponse.
        """
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "data": None,
                "error": {"code": "internal_error", "details": None},
            },
        )
