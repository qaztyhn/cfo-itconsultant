"""Phân trang và ?sort= dùng chung cho API đọc (06 mục 1, 13.1)."""

import pytest

from app.core.errors import DomainError
from app.services.query_utils import parse_sort


def test_parse_sort_default_and_multiple_fields() -> None:
    allowed = frozenset({"code", "name", "type"})
    assert parse_sort(None, allowed, "code") == [("code", False)]
    assert parse_sort("-name,code", allowed, "code") == [("name", True), ("code", False)]
    assert parse_sort(" type , -code ", allowed, "code") == [("type", False), ("code", True)]


@pytest.mark.parametrize("raw", ["unknown", "-", "code,,name", "name;drop"])
def test_parse_sort_rejects_unknown_or_malformed_fields(raw: str) -> None:
    with pytest.raises(DomainError) as caught:
        parse_sort(raw, frozenset({"code", "name"}), "code")
    assert caught.value.code == "VALIDATION_ERROR" and caught.value.http_status == 422
