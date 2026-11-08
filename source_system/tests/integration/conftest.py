"""Shared isolated HTTP/database fixture for source lifecycle acceptance tests."""

from tests.integration.test_order_writes import source as order_source

__all__ = ["order_source"]
