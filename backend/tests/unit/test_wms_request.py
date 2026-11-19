import json
from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.services import wms_request

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
}
UNITS = {"SE-CEM-MOR-25": Decimal(1)}


def test_native_evidence_returns_relation_version_and_warehouse_skus() -> None:
    relations, versions, skus = wms_request.native_evidence(FIXTURE, "SE", "GBG", UNITS)
    assert [(r.local_sku, r.wms_sku, r.stock_unit, r.confirmed) for r in relations] == [
        ("SE-CEM-MOR-25", "WMS-CEM-25", "bag", True)
    ]
    assert versions == {"SE-CEM-MOR-25": "synthetic:confirmed-v1"}
    assert skus == {("GBG", "WMS-CEM-25")}


def test_other_warehouse_and_unknown_sku_yield_no_relations() -> None:
    assert wms_request.native_evidence(FIXTURE, "SE", "XXX", UNITS)[0] == []
    assert wms_request.native_evidence(FIXTURE, "SE", "GBG", {})[0] == []


def test_wrong_market_and_malformed_fixture_are_409() -> None:
    with pytest.raises(DomainError) as wrong:
        wms_request.native_evidence(FIXTURE, "NO", "GBG", UNITS)
    assert wrong.value.code == "PLAN_NOT_APPROVABLE"
    with pytest.raises(DomainError) as bad:
        wms_request.native_evidence({"market": "SE", "mapping": [{}]}, "SE", "GBG", UNITS)
    assert bad.value.code == "PLAN_NOT_APPROVABLE"


def test_load_fixture_requires_absolute_existing_disposable_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SYNTHETIC_WMS_FIXTURE", raising=False)
    with pytest.raises(DomainError):
        wms_request.load_fixture()
    monkeypatch.setenv("SYNTHETIC_WMS_FIXTURE", "relative.json")
    with pytest.raises(DomainError):
        wms_request.load_fixture()
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"source_kind": "real"}), encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_WMS_FIXTURE", str(path))
    with pytest.raises(DomainError):
        wms_request.load_fixture()
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    assert wms_request.load_fixture()["market"] == "SE"
