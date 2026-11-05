"""Declarative Base và mixin created_at/updated_at (05 mục 1)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base cho mọi model CFO."""
