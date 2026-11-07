"""Sinh điểm danh planned 14 ngày tới từ ca mẫu (06 v1.4 mục 13.2, Q11 = B).

Một lượt = một transaction; chạy lại không tạo trùng (chỉ thêm cho người chưa có dòng của ngày đó).
Lịch chạy do scheduler (Dev 2) đăng ký.

Owner: Dev 1 (A) — M3.
"""

from app.core.db import get_sessionmaker, session_scope
from app.services.hr_service import generate_attendance


async def run() -> int:
    """Chạy một lượt; trả số bản ghi tạo mới."""
    async for session in session_scope(get_sessionmaker()):
        return await generate_attendance(session)
    return 0
