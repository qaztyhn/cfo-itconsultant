"""Unit contract tests for prospective WMS reservation readiness; no real WMS writes."""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.services.wms_reservation_readiness import (
    ReserveAck,
    VerifiedSourceLine,
    WmsLine,
    prepare_intent,
    require_full_ack,
    require_snapshot_inclusion,
)


def source(**changes: object) -> VerifiedSourceLine:
    line = VerifiedSourceLine(
        order_id=10,
        line_no=1,
        market_id=2,
        warehouse_id=3,
        global_product_id=4,
        pos_sku="POS-25",
        wms_sku="WMS-BAG25",
        wms_unit="bag",
        mapping_version="mapping-rev-4",
        source_version=7,
        sale_quantity=Decimal("5"),
        units_to_base=Decimal("20"),
        base_units_per_wms_unit=Decimal("1"),
        wms_quantity_scale=0,
        mapping_confirmed=True,
        pos_wms_relation_verified=True,
        warehouse_allocation_verified=True,
        snapshot_complete_and_fresh=True,
    )
    return replace(line, **changes)


def intent():
    return prepare_intent((source(),), idempotency_key="stable-order-10-v7")


def accepts():
    request = intent()
    ack = ReserveAck(
        idempotency_key=request.idempotency_key,
        reservation_id="wms-resv-001",
        status="accepted",
        lines=request.lines,
    )
    return request, ack


@pytest.mark.parametrize(
    "change",
    [
        {"mapping_confirmed": False},
        {"pos_wms_relation_verified": False},
        {"warehouse_allocation_verified": False},
        {"snapshot_complete_and_fresh": False},
        {"wms_sku": ""},
        {"wms_unit": ""},
        {"mapping_version": ""},
        {"units_to_base": Decimal("0")},
        {"base_units_per_wms_unit": Decimal("0")},
        {"sale_quantity": Decimal("-1")},
    ],
)
def test_WMS_reverse_sku_unverified_provenance_never_creates_intent(
    change: dict[str, object],
) -> None:
    with pytest.raises(DomainError) as error:
        prepare_intent((source(**change),), idempotency_key="stable")
    assert error.value.code == "PLAN_NOT_APPROVABLE"


def test_WMS_original_source_sku_is_preserved_and_quantity_is_exact() -> None:
    request = intent()
    assert request.lines == (
        WmsLine(
            line_no=1,
            warehouse_id=3,
            wms_sku="WMS-BAG25",
            wms_unit="bag",
            quantity=Decimal("100"),
        ),
    )
    assert request.market_id == 2 and request.source_version == 7


def test_WMS_multiple_local_skus_same_global_keep_distinct_original_lines() -> None:
    request = prepare_intent(
        (
            source(),
            source(
                line_no=2,
                pos_sku="POS-50",
                wms_sku="WMS-BAG50",
                sale_quantity=Decimal("2"),
            ),
        ),
        idempotency_key="same-order-one-reservation",
    )
    assert [line.wms_sku for line in request.lines] == ["WMS-BAG25", "WMS-BAG50"]
    assert len(request.lines) == 2  # one request, not a request per vehicle


def test_WMS_duplicate_line_or_mixed_order_warehouse_source_version_rejected() -> None:
    for duplicate in (
        source(),
        source(line_no=2, order_id=11),
        source(line_no=2, warehouse_id=8),
        source(line_no=2, source_version=8),
        source(line_no=2, market_id=7),
    ):
        with pytest.raises(DomainError, match=""):
            prepare_intent((source(), duplicate), idempotency_key="one-key")


@pytest.mark.parametrize(
    "quantity,scale",
    [(Decimal("0.25"), 0), (Decimal("0.0001"), 3), (Decimal("1"), 4)],
)
def test_WMS_fractional_or_unverified_precision_fails_without_rounding(quantity: Decimal, scale: int) -> None:
    with pytest.raises(DomainError) as error:
        prepare_intent(
            (
                source(
                    sale_quantity=quantity,
                    units_to_base=Decimal("1"),
                    wms_quantity_scale=scale,
                ),
            ),
            idempotency_key="stable",
        )
    assert error.value.code == "PLAN_NOT_APPROVABLE"


@pytest.mark.parametrize(
    "change",
    [
        {"idempotency_key": "new-key"},
        {"reservation_id": ""},
        {"status": "pending"},
        {"status": "partially_accepted"},
        {"status": "rejected"},
        {"lines": ()},
    ],
)
def test_WMS_timeout_partial_rejection_and_unknown_status_never_guarantee_stock(
    change: dict[str, object],
) -> None:
    request, ack = accepts()
    with pytest.raises(DomainError) as error:
        require_full_ack(request, replace(ack, **change))
    assert error.value.code == "PLAN_NOT_APPROVABLE"


def test_WMS_no_ack_timeout_is_not_approval() -> None:
    with pytest.raises(DomainError) as error:
        require_full_ack(intent(), None)
    assert error.value.code == "PLAN_NOT_APPROVABLE"


@pytest.mark.parametrize(
    "wrong",
    [
        WmsLine(1, 3, "WMS-OTHER", "bag", Decimal("100")),
        WmsLine(1, 4, "WMS-BAG25", "bag", Decimal("100")),
        WmsLine(1, 3, "WMS-BAG25", "pallet", Decimal("100")),
        WmsLine(1, 3, "WMS-BAG25", "bag", Decimal("99")),
        WmsLine(2, 3, "WMS-BAG25", "bag", Decimal("100")),
    ],
)
def test_WMS_ack_wrong_sku_warehouse_unit_qty_or_line_rejected(wrong: WmsLine) -> None:
    request, ack = accepts()
    with pytest.raises(DomainError):
        require_full_ack(request, replace(ack, lines=(wrong,)))


def test_WMS_exact_ack_returns_external_identity_not_cfo_approval() -> None:
    request, ack = accepts()
    assert require_full_ack(request, ack) == "wms-resv-001"


def test_WMS_delayed_snapshot_or_timestamp_alone_cannot_clear_protection() -> None:
    for proof in (None, frozenset(), frozenset({"unrelated-reservation"})):
        with pytest.raises(DomainError) as error:
            require_snapshot_inclusion("wms-resv-001", authoritative_included_reservation_ids=proof)
        assert error.value.code == "PLAN_NOT_APPROVABLE"


def test_WMS_matching_inclusion_evidence_avoids_double_deduction() -> None:
    require_snapshot_inclusion(
        "wms-resv-001",
        authoritative_included_reservation_ids=frozenset({"wms-resv-001"}),
    )
