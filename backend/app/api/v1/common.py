"""Schema và tham số dùng chung cho API đọc có phân trang (06 mục 1).

Owner: Dev 1 (A) — M1.
"""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class Page[T](BaseModel):
    """`{ "items": [...], "page": 1, "page_size": 50, "total": 123 }` (06 mục 1)."""

    items: list[T]
    page: int
    page_size: int
    total: int


PageNo = Annotated[int, Query(ge=1, description="Trang, bắt đầu từ 1")]
PageSize = Annotated[int, Query(ge=1, le=200, description="Số dòng mỗi trang (tối đa 200)")]
SortParam = Annotated[str | None, Query(description="Ví dụ `-name,code`; tiền tố `-` = giảm dần")]
