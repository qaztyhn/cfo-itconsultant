"""FastAPI application factory.

- Gắn middleware correlation_id (core.correlation), handler lỗi chuẩn (core.errors).
- Mount router /api/v1 (api.v1.*) và /internal (api.v1.internal).
- Khởi động APScheduler (jobs.scheduler) khi APP_ENV != "test".
- CORS chỉ cho origin cấu hình (09 mục 10).

Owner: Dev 1 (luồng A) — M0.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core import clock
from app.core.config import get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Tạo ứng dụng FastAPI với middleware, lỗi chuẩn và router v1."""
    settings = get_settings()
    if settings.app_now:  # chỉ cố định đồng hồ khi APP_NOW được đặt (08 mục 1.6)
        clock.init_from_settings(settings.app_now)
    configure_logging(Path("logs") if settings.app_env == "local" else None)
    app = FastAPI(title="CFO API", version="0.1.0", docs_url="/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(api_v1_router, prefix="/api/v1")
    app.state.settings = settings
    return app


app = create_app()
