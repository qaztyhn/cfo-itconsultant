"""Model SQLAlchemy 2.0 theo 6 schema của docs/05 (ref, hr, stg, ops, plan, audit).

Tên bảng/cột y hệt 05. Mỗi schema một module. Base dùng chung ở base.py.
Owner: Dev 1 (luồng A) — M1.
"""

from app.domain.models import hr, ref
from app.domain.models.base import Base

__all__ = ["Base", "hr", "ref"]
