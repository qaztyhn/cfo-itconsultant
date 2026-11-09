"""Disposable WMS HTTP + persistent SQLite acceptance: never an approval E2E."""

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.disposable_wms_service import FROZEN, create_app, verify_batch

KEY = "synthetic-disposable-local-only-key-1234567890"
FIXTURE = {
    "source_kind": "synthetic_demo",
    "market": "SE",
    "stock": [{"warehouse_code": "GBG", "wms_sku": "WMS-CEM-25", "wms_unit": "bag", "on_hand": "100.000"}],
    "mapping": [
        {
            "market": "SE",
            "warehouse_code": "GBG",
            "pos_sku": "SE-CEM-MOR-25",
            "wms_sku": "WMS-CEM-25",
            "wms_unit": "bag",
            "mapping_version": "synthetic:confirmed-v1",
            "confirmed": True,
        }
    ],
    "source_orders": [
        {
            "order_id": 50,
            "plan_id": 80,
            "source_version": 2,
            "source_ref": "SYN-POS-50",
            "lines": [
                {
                    "order_line_id": 99,
                    "pos_sku": "SE-CEM-MOR-25",
                    "warehouse_code": "GBG",
                    "quantity": "60.000",
                }
            ],
        },
        {
            "order_id": 51,
            "plan_id": 81,
            "source_version": 2,
            "source_ref": "SYN-POS-51",
            "lines": [
                {
                    "order_line_id": 100,
                    "pos_sku": "SE-CEM-MOR-25",
                    "warehouse_code": "GBG",
                    "quantity": "50.000",
                }
            ],
        },
    ],
}
REQUEST = {
    "market": "SE",
    "order_id": 50,
    "plan_id": 80,
    "source_version": 2,
    "idempotency_key": "cfo-res-test-immutable",
    "source_ref": "SYN-POS-50",
    "lines": [
        {
            "order_line_id": 99,
            "pos_sku": "SE-CEM-MOR-25",
            "wms_sku": "WMS-CEM-25",
            "warehouse_code": "GBG",
            "wms_unit": "bag",
            "mapping_version": "synthetic:confirmed-v1",
            "quantity": "60.000",
        }
    ],
}
HEADERS = {"X-Demo-WMS-Key": KEY}


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setenv("APP_NOW", FROZEN)
    monkeypatch.delenv("WMS_PRODUCTION_ENABLED", raising=False)
    return tmp_path / "persistent-synthetic-wms.sqlite3"


def _client(db: Path, spec=FIXTURE) -> TestClient:
    return TestClient(create_app(db, KEY, spec))


def test_reserve_status_restart_release_and_authenticated_inclusion(database: Path):
    with _client(database) as client:
        assert client.get("/v1/stock").status_code == 401
        before = client.get("/v1/stock", headers=HEADERS).json()
        assert before["complete"] is True
        assert before["item_count"] == 1
        assert before["items"][0]["on_hand"] == "100.000"
        r = client.post("/v1/reserve", json=REQUEST, headers=HEADERS)
        assert r.status_code == 200, r.text
        ack = r.json()
        assert ack["status"] == "accepted" and ack["source_version"] == 2
        assert ack["lines"][0]["wms_sku"] == "WMS-CEM-25"
        assert client.post("/v1/reserve", json=REQUEST, headers=HEADERS).json() == ack
        included = client.get("/v1/stock", headers=HEADERS).json()
        assert included["batch_id"] == ack["reflected_in_batch_id"]
        assert included["items"][0]["reserved"] == "60.000"
        assert included["items"][0]["on_hand"] == "100.000"
        assert verify_batch(included, KEY, expected_reservation_id=ack["reservation_id"])
        assert not verify_batch(before, KEY, expected_reservation_id=ack["reservation_id"])

    # Process restart: new app/DB connection, same on-disk state and immutable request.
    with _client(database) as restarted:
        status = restarted.get(f"/v1/status/SE/{REQUEST['idempotency_key']}", headers=HEADERS)
        assert status.status_code == 200 and status.json() == ack
        assert restarted.post("/v1/reserve", json=REQUEST, headers=HEADERS).json() == ack
        release = {
            "market": "SE",
            "reservation_id": ack["reservation_id"],
            "idempotency_key": REQUEST["idempotency_key"] + ":release",
        }
        done = restarted.post("/v1/release", json=release, headers=HEADERS)
        assert done.status_code == 200 and done.json()["status"] == "released"
        assert restarted.post("/v1/release", json=release, headers=HEADERS).json() == done.json()
        final = restarted.get("/v1/stock", headers=HEADERS).json()
        assert final["items"][0]["reserved"] == "0.000"
        assert ack["reservation_id"] not in final["included_reservation_ids"]
        assert not verify_batch(final, KEY, expected_reservation_id=ack["reservation_id"])


def test_wrong_sku_unit_warehouse_mapping_version_and_scope_fail_closed(database: Path):
    with _client(database) as client:
        for field, value in [
            ("wms_sku", "SE-CEM-MOR-25"),  # same POS code cannot be assumed WMS-native
            ("wms_unit", "each"),
            ("warehouse_code", "STO"),
            ("mapping_version", "synthetic:unapproved-v2"),
            ("pos_sku", "OTHER"),
        ]:
            bad = copy.deepcopy(REQUEST)
            bad["idempotency_key"] = "test-" + field
            bad["lines"][0][field] = value
            assert client.post("/v1/reserve", json=bad, headers=HEADERS).status_code == 409
        bad = copy.deepcopy(REQUEST)
        bad["market"] = "NO"
        assert client.post("/v1/reserve", json=bad, headers=HEADERS).status_code == 409
        unchanged = client.get("/v1/stock", headers=HEADERS).json()
        assert unchanged["batch_id"] == 1 and unchanged["items"][0]["reserved"] == "0.000"


def test_stock_capacity_idempotency_collision_partial_and_tamper_denied(database: Path):
    with _client(database) as client:
        assert client.post("/v1/reserve", json=REQUEST, headers=HEADERS).status_code == 200
        tampered = copy.deepcopy(REQUEST)
        tampered["source_version"] = 3
        # Version is checked against pinned Source evidence, not the caller claim.
        assert client.post("/v1/reserve", json=tampered, headers=HEADERS).status_code == 409
        excessive = copy.deepcopy(REQUEST)
        excessive["idempotency_key"] = "new-distinct-request"
        excessive["order_id"] = 51
        excessive["plan_id"] = 81
        excessive["source_ref"] = "SYN-POS-51"
        excessive["lines"][0]["order_line_id"] = 100
        excessive["lines"][0]["quantity"] = "50.000"
        assert client.post("/v1/reserve", json=excessive, headers=HEADERS).status_code == 409
        partial = copy.deepcopy(REQUEST)
        partial["idempotency_key"] = "never-partial"
        partial["lines"] *= 2
        assert client.post("/v1/reserve", json=partial, headers=HEADERS).status_code == 409
        changed = client.get("/v1/stock", headers=HEADERS).json()
        assert changed["batch_id"] == 2
        bad_sig = copy.deepcopy(changed)
        bad_sig["items"][0]["reserved"] = "1.000"
        assert not verify_batch(bad_sig, KEY, expected_reservation_id=changed["included_reservation_ids"][0])
        no_include = copy.deepcopy(changed)
        no_include["included_reservation_ids"] = []
        assert not verify_batch(
            no_include, KEY, expected_reservation_id=changed["included_reservation_ids"][0]
        )
        assert client.get("/v1/status/SE/wrong", headers=HEADERS).status_code == 404


def test_disposable_security_and_immutable_fixture(database: Path, monkeypatch: pytest.MonkeyPatch):
    with _client(database) as client:
        bad_fixture = copy.deepcopy(FIXTURE)
        bad_fixture["mapping"][0]["mapping_version"] = "synthetic:unreviewed-v2"
        with pytest.raises(ValueError, match="cannot be reseeded"):
            create_app(database, KEY, bad_fixture)
        monkeypatch.setenv("APP_ENV", "production")
        assert client.post("/v1/reserve", json=REQUEST, headers=HEADERS).status_code == 503
        with pytest.raises(RuntimeError, match="Disposable WMS"):
            create_app(database, KEY, FIXTURE)
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("WMS_PRODUCTION_ENABLED", "1")
        assert client.get("/v1/stock", headers=HEADERS).status_code == 503
