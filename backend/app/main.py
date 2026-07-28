"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.logging import setup_logging
from app.core.redis import close_redis_connection, connect_to_redis
from app.core.telemetry import setup_telemetry
from app.middleware.exception_handlers import RequestLoggingMiddleware, register_exception_handlers
from app.routers.api import api_v1_router
from app.routers.websocket import router as websocket_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown resources.

    Args:
        _: FastAPI application instance.

    Yields:
        Control to the running application.
    """
    setup_logging()
    settings = get_settings()
    # Re-read .env on process (re)start so key rotations take effect with --reload.
    from app.core.config import clear_settings_cache

    clear_settings_cache()
    settings = get_settings()
    setup_telemetry(settings)
    await connect_to_mongo()
    await connect_to_redis()
    yield
    await close_redis_connection()
    await close_mongo_connection()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance.
    """
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(application)
    application.include_router(api_v1_router)
    application.include_router(websocket_router)

    if settings.otel_enabled:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(application)
        except Exception:
            # Telemetry must never prevent the API from starting.
            pass

    @application.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Simple health payload.
        """
        return {"status": "ok"}

    return application


app = create_app()
