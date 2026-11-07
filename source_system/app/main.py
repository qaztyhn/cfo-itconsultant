"""Source FastAPI foundation (M0); business endpoints remain M1 work."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health_router, router
from app.auth import SourceAuthenticationError, authentication_error
from app.config import Settings
from app.db import create_engine


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
    application.include_router(router, prefix="/api/v1")
    application.include_router(health_router, prefix="/api/v1")
    application.add_exception_handler(SourceAuthenticationError, authentication_error)
    return application


app = create_app()
