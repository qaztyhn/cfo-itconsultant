"""DEC-R3-15 / API §19.1 against the published app and its generated schema."""

from fastapi import FastAPI

from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute
from tests.integration.hr_fixture import ADMIN, DISPATCHER, SETUP, WAREHOUSE

RETIRED = (
    ("GET", "/transfers"),
    ("POST", "/orders/{order_id}/transfers"),
    ("POST", "/transfers/{transfer_id}/confirm-source"),
    ("POST", "/transfers/{transfer_id}/receive"),
    ("POST", "/transfers/{transfer_id}/cancel"),
    ("GET", "/orders/{order_id}/transfer-suggestions"),
    ("GET", "/users"),
    ("POST", "/users/{user_id}/reset-password"),
    ("POST", "/employees"),
    ("POST", "/employees/{employee_id}/assignments"),
    ("POST", "/employees/{employee_id}/terminate"),
    ("POST", "/vehicles"),
    ("GET", "/markets/{code}/config"),
    ("PUT", "/markets/{code}/config"),
    ("GET", "/warehouses/{warehouse_id}/shift-templates"),
    ("PUT", "/warehouses/{warehouse_id}/shift-templates"),
    ("POST", "/absences"),
)


def test_DEC_R3_15_retired_operations_are_absent_from_openapi() -> None:
    from app.main import create_app

    app: FastAPI = create_app()
    paths = app.openapi()["paths"]
    for method, path in RETIRED:
        assert method.lower() not in paths.get("/api/v1" + path, {})
    for path in ("/employees", "/vehicles", "/locations", "/warehouses/{warehouse_id}/capacity"):
        assert "get" in paths["/api/v1" + path]
    assert "post" in paths["/api/v1/orders/{order_id}/plan"]


def test_DEC_R3_15_retired_operations_return_404_for_all_callers(api: Api) -> None:  # noqa: F811
    execute(api.dsn, *SETUP)
    for user in (ADMIN, DISPATCHER, WAREHOUSE):
        assert api.get("/auth/me", user).status_code == 200
    for method, template in RETIRED:
        path = template.format(order_id=1, transfer_id=1, user_id=1, employee_id=4, code="SE", warehouse_id=1)
        for user in (ADMIN, DISPATCHER, WAREHOUSE, None):
            response = api.send(method, path, user)
            assert_error(response, 404, "NOT_FOUND")
            assert response.headers["X-Correlation-ID"] == response.json()["error"]["correlation_id"]
    for method, path in (("PATCH", "/employees"), ("POST", "/vehicles/1"), ("POST", "/locations")):
        response = api.send(method, path, ADMIN)
        assert response.status_code == 405
        assert response.headers["Allow"] == "GET"
