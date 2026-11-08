from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.errors import ErrorEnvelope
from app.main import create_app


def test_US_SRC_02_AC1_implemented_openapi_is_shared_by_two_instances_and_matches_candidate() -> None:
    first = create_app(Settings("postgresql+asyncpg://localhost/source", "src_se", "synthetic-one")).openapi()
    second = create_app(
        Settings("postgresql+asyncpg://localhost/source", "src_shadow", "synthetic-two")
    ).openapi()
    assert first == second
    baseline = yaml.safe_load((Path(__file__).parents[2] / "openapi.yaml").read_text(encoding="utf-8"))
    assert first == baseline
    stock = first["paths"]["/api/v1/stock"]["get"]
    assert stock["responses"]["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorEnvelope"
    )
    stock_properties = first["components"]["schemas"]["StockSnapshot"]["properties"]
    assert {"as_of", "batch_id", "item_count", "items"} <= set(stock_properties)
    assert "physical_stock_pool_id" not in str(first)
    expected = {
        "/orders": {"get", "post"},
        "/orders/{order_id}": {"put"},
        "/orders/{order_id}/validate": {"post"},
        "/orders/{order_id}/submit": {"post"},
        "/orders/{order_id}/cancel": {"post"},
        **{
            path: {"get"}
            for path in (
                "/customers",
                "/products",
                "/stock",
                "/inbound",
                "/fleet/calendar",
                "/addresses",
                "/health",
            )
        },
    }
    assert set(first["paths"]) == {"/api/v1" + path for path in expected}
    for path, methods in expected.items():
        assert set(first["paths"]["/api/v1" + path]) == methods
        for method in methods:
            operation = first["paths"]["/api/v1" + path][method]
            if path == "/health":
                assert "security" not in operation and "503" in operation["responses"]
            else:
                assert operation["security"] == [{"APIKeyHeader": []}]
                assert operation["responses"]["422"]["content"]["application/json"]["schema"][
                    "$ref"
                ].endswith("/ErrorEnvelope")
    assert "synthetic-one" not in str(first) and "synthetic-two" not in str(first)


@pytest.mark.parametrize(
    "body",
    [
        {"code": "AUTH_INVALID", "message": "Invalid API key.", "details": {}},
        {
            "code": "VALIDATION_ERROR",
            "message": "Invalid fields.",
            "details": {
                "errors": [
                    {
                        "loc": ["body", "lines", 0, "qty"],
                        "type": "invalid_quantity",
                        "msg": "Quantity invalid.",
                    }
                ]
            },
        },
    ],
)
def test_US_SRC_02_AC1_error_contract_covers_auth_and_business_validation(body: dict[str, object]) -> None:
    envelope = ErrorEnvelope.model_validate(
        {"error": {**body, "correlation_id": "00000000-0000-4000-8000-000000000001"}}
    )
    assert envelope.error.code == body["code"]
