"""Tiện ích truy vấn dùng chung cho API đọc: phân trang và ?sort= (06 mục 1, 13.1).

Owner: Dev 1 (A) — M1.
"""

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError

_FIELD = re.compile(r"-?[a-z_]+")


def parse_sort(raw: str | None, allowed: frozenset[str], default: str) -> list[tuple[str, bool]]:
    """`-a,b` → [("a", desc=True), ("b", desc=False)]; trường ngoài `allowed` hoặc sai cú pháp → 422."""
    text = raw if raw is not None and raw.strip() else default
    result: list[tuple[str, bool]] = []
    for part in text.split(","):
        token = part.strip()
        if not _FIELD.fullmatch(token) or token.lstrip("-") not in allowed:
            raise DomainError(
                "VALIDATION_ERROR", f"Unsupported sort field '{token}'.", {"allowed": sorted(allowed)}
            )
        result.append((token.lstrip("-"), token.startswith("-")))
    return result


async def paginate(
    session: AsyncSession, query: Select[Any], *, page: int, page_size: int
) -> tuple[Sequence[Any], int]:
    """Trả (các phần tử của trang, tổng số) cho một truy vấn ORM đã sắp xếp."""
    total = (
        await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    ).scalar_one()
    items = (await session.execute(query.limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return items, int(total)
