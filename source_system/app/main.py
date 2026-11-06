"""Source FastAPI foundation (M0); business endpoints remain M1 work."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.config import Settings
from app.db import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings or Settings.from_env())
        app.state.engine = engine
        try:
            yield
        finally:
            await engine.dispose()

    application = FastAPI(title="CFO Source System (mock)", version="0.1.0", lifespan=lifespan)
    application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
