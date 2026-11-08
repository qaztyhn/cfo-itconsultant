"""Isolated source instance implementing the approved D1 source contract; never writes CFO."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import Response

from app.api import health_router, router
from app.auth import SourceAuthenticationError, authentication_error
from app.config import Settings
from app.db import create_engine
from app.errors import SourceOrderError, StockUnavailable, order_error, request_id, stock_unavailable, validation_error


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings or Settings.from_env()
        engine = create_engine(app.state.settings)
        app.state.engine = engine
        try:
            yield
        finally:
            await engine.dispose()

    application = FastAPI(title="CFO Source System (mock)", version="0.1.0", lifespan=lifespan)

    @application.middleware("http")
    async def correlate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        correlation_id = request_id(request)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    application.include_router(router, prefix="/api/v1")
    application.include_router(health_router, prefix="/api/v1")
    application.add_exception_handler(SourceAuthenticationError, authentication_error)
    application.add_exception_handler(StockUnavailable, stock_unavailable)
    application.add_exception_handler(RequestValidationError, validation_error)
    application.add_exception_handler(SourceOrderError, order_error)
    return application


app = create_app()
