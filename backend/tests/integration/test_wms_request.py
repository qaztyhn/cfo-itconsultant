import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan
from app.services import wms_request
from tests.integration.conftest import execute
from tests.integration.test_approval_service import _run
from tests.integration.test_approval_service import db as db  # noqa: F401

pytestmark = pytest.mark.integration


def _fixture(tmp_path, monkeypatch, *, confirmed: bool = True, stocked: bool = True) -> None:
    data = {
        "source_kind": "synthetic_demo",
        "market": "SE",
        "stock": (
            [{"warehouse_code": "WH-1", "wms_sku": "WMS-1", "wms_unit": "pcs", "on_hand": "100.000"}]
            if stocked
            else []
        ),
        "mapping": [
            {
                "market": "SE",
                "warehouse_code": "WH-1",
                "pos_sku": "SKU1",
                "wms_sku": "WMS-1",
                "wms_unit": "pcs",
                "mapping_version": "synthetic:confirmed-v1",
                "confirmed": confirmed,
            }
        ],
    }
    path = tmp_path / "wms.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_WMS_FIXTURE", str(path))


def _product(db: str, status: str = "confirmed") -> None:
    execute(
        db,
        "INSERT INTO ref.product_se (local_sku,name,category,sale_unit,units_to_base,unit_price,"
        "global_product_id,mapping_status,mapped_by) "
        f"VALUES ('SKU1','Sack','Cement','pcs',1,1,1,'{status}',1)",
    )


async def _build(session: AsyncSession) -> wms_request.BuiltRequest:
    order = await session.get(CustomerOrder, 1)
    plan = await session.get(FulfilmentPlan, 1)
    assert order is not None and plan is not None
    return await wms_request.build_simulated_request(session, order, plan)


def test_builds_exact_server_side_request(db: str, tmp_path, monkeypatch) -> None:
    _fixture(tmp_path, monkeypatch)
    _product(db)
    built = _run(db, _build)
    again = _run(db, _build)
    assert built.request == again.request  # khóa idempotency ổn định giữa các lần retry
    assert built.request.market == "SE" and built.request.order_id == 1 and built.request.plan_id == 1
    assert built.source_ref == "EXT-1" and built.source_version == 1
    (line,) = built.request.lines
    actual = (line.pos_sku, line.wms_sku, line.warehouse_code, line.wms_unit)
    assert actual == ("SKU1", "WMS-1", "WH-1", "pcs")
    assert line.quantity == Decimal("20")
    assert line.mapping_version == "synthetic:confirmed-v1"


@pytest.mark.parametrize(
    "case", ["no_product", "pending_product", "unconfirmed_fixture", "sku_not_in_warehouse"]
)
def test_unverified_evidence_is_409(db: str, tmp_path, monkeypatch, case: str) -> None:
    _fixture(
        tmp_path,
        monkeypatch,
        confirmed=case != "unconfirmed_fixture",
        stocked=case != "sku_not_in_warehouse",
    )
    if case != "no_product":
        _product(db, "pending" if case == "pending_product" else "confirmed")
    with pytest.raises(DomainError) as caught:
        _run(db, _build)
    assert caught.value.code == "PLAN_NOT_APPROVABLE"
