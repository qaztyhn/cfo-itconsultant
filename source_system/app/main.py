"""FastAPI của hệ thống nguồn `source-<cc>` (06 mục 16). Xác thực X-API-Key. Cổng 8100.

Owner: Dev 2 (luồng B) — M0/M1.
"""
from fastapi import FastAPI

from app.api import router

app = FastAPI(title="CFO Source System (mock)", version="0.1.0")
app.include_router(router, prefix="/api/v1")
