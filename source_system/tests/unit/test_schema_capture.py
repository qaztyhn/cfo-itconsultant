"""Temporary CI-only schema capture for D1 contract reconciliation."""

import yaml

from app.main import app


def test_capture_generated_openapi() -> None:
    print("SCHEMA_CAPTURE_BEGIN_106")
    print(yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False))
    print("SCHEMA_CAPTURE_END_106")
    raise AssertionError("SCHEMA_CAPTURE_ONLY")
