"""WMS reservation adapter contract tests against an in-memory FAKE WMS (the real WMS API is unverified)."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.adapters.base import StockItemDTO, StockSnapshotDTO
from app.adapters.stock_accounting import CfoCommitment, compute_availability
from app.adapters.stock_refresh import StockRefreshFailed, refresh_after_ack
from app.adapters.wms_reservation import (
    AckLine,
    DisabledWmsPort,
    ReservationAck,
    ReservationMismatch,
    ReservationRequest,
    ReservationUnknown,
    WmsDisabled,
    WmsRejected,
    WmsTimeout,
    WmsUnavailable,
    build_request,
    idempotency_key,
    reserve_with_recovery,
)
from app.adapters.wms_sku import (
    ConfirmedMapping,
    OrderLineRef,
    ReverseSkuError,
    WmsSkuRelation,
    resolve_reservation_lines,
)

D = Decimal


class FakeWms:
    """Atomic availability check, idempotent by key, with injectable faults."""

    def __init__(self, available: dict[tuple[str, str], Decimal]) -> None:
        self.available = dict(available)
        self.by_key: dict[str, ReservationAck] = {}
        self.calls: list[str] = []
        self.lock = asyncio.Lock()
        self.timeout_after_commit = 0  # reserve commits but the ACK is lost
        self.timeout_before_commit = 0  # reserve never reaches WMS
        self.status_timeouts = 0
        self.mode = "normal"  # normal | partial | wrong_sku | reject

    async def reserve(self, request: ReservationRequest) -> ReservationAck:
        self.calls.append("reserve")
        if self.timeout_before_commit:
            self.timeout_before_commit -= 1
            raise WmsTimeout()
        async with self.lock:
            if request.idempotency_key in self.by_key:  # duplicate key: same ack, no double reservation
                ack = self.by_key[request.idempotency_key]
            elif self.mode == "reject" or any(
                self.available.get((ln.warehouse_code, ln.wms_sku), D(0)) < ln.quantity
                for ln in request.lines
            ):
                ack = ReservationAck("", "rejected", (), "0")
                self.by_key[request.idempotency_key] = ack
            else:
                lines = [AckLine(ln.wms_sku, ln.warehouse_code, ln.quantity) for ln in request.lines]
                if self.mode == "partial":
                    lines[0] = AckLine(lines[0].wms_sku, lines[0].warehouse_code, lines[0].quantity - 1)
                    status = "partial"
                else:
                    status = "accepted"
                if self.mode == "wrong_sku":
                    lines[0] = AckLine("OTHER", lines[0].warehouse_code, lines[0].quantity)
                for ln in request.lines:
                    self.available[(ln.warehouse_code, ln.wms_sku)] -= ln.quantity
                ack = ReservationAck(f"R-{len(self.by_key) + 1}", status, tuple(lines), "7", 12)
                self.by_key[request.idempotency_key] = ack
        if self.timeout_after_commit:
            self.timeout_after_commit -= 1
            raise WmsTimeout()
        return ack

    async def status(self, market: str, idempotency_key: str) -> ReservationAck | None:
        self.calls.append("status")
        if self.status_timeouts:
            self.status_timeouts -= 1
            raise WmsUnavailable()
        return self.by_key.get(idempotency_key)

    async def release(self, market: str, reservation_id: str, idempotency_key: str) -> ReservationAck:
        self.calls.append("release")
        return ReservationAck(reservation_id, "released", (), "8")


def lines(qty: str = "40") -> tuple:
    mapping = ConfirmedMapping("POS-1", 10, "bag", D("2.5"), True, "v1")
    rel = WmsSkuRelation("SE", "WH-1", "POS-1", "W-9", "bag", D("2.5"), False, True)
    ref = OrderLineRef(1, "POS-1", 10, D(qty) * D("2.5"), "v1")
    return resolve_reservation_lines("SE", "WH-1", [ref], {"POS-1": mapping}, [rel], {("WH-1", "W-9")})


def request(qty: str = "40") -> ReservationRequest:
    return build_request("SE", 1, 5, lines(qty))


# --- reverse SKU ---------------------------------------------------------------------------------------


def test_reverse_sku_uses_the_wms_native_sku_and_exact_stock_unit_quantity() -> None:
    [line] = lines("40")
    assert (line.pos_sku, line.wms_sku, line.warehouse_code, line.wms_unit) == ("POS-1", "W-9", "WH-1", "bag")
    assert line.quantity == D(40) and line.mapping_version == "v1"


def _resolve(**over):
    base = {
        "mappings": {"POS-1": ConfirmedMapping("POS-1", 10, "bag", D("2.5"), True, "v1")},
        "relations": [WmsSkuRelation("SE", "WH-1", "POS-1", "W-9", "bag", D("2.5"), False, True)],
        "warehouse_skus": {("WH-1", "W-9")},
        "line": OrderLineRef(1, "POS-1", 10, D("100"), "v1"),
        "market": "SE",
    }
    base.update(over)
    return resolve_reservation_lines(
        base["market"], "WH-1", [base["line"]], base["mappings"], base["relations"], base["warehouse_skus"]
    )


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"relations": []}, "WMS_SKU_NOT_VERIFIED"),  # POS SKU == WMS SKU is never assumed
        (
            {"relations": [WmsSkuRelation("SE", "WH-1", "POS-1", "W-9", "bag", D("2.5"), False, False)]},
            "WMS_SKU_NOT_VERIFIED",
        ),
        (
            {
                "relations": [
                    WmsSkuRelation("SE", "WH-1", "POS-1", "W-9", "bag", D("2.5"), False, True),
                    WmsSkuRelation("SE", "WH-1", "POS-1", "W-8", "bag", D("2.5"), False, True),
                ]
            },
            "WMS_SKU_AMBIGUOUS",  # never the first match
        ),
        ({"market": "DK"}, "WMS_SKU_NOT_VERIFIED"),  # relation of another market
        ({"warehouse_skus": set()}, "WMS_SKU_NOT_IN_WAREHOUSE"),
        (
            {"mappings": {"POS-1": ConfirmedMapping("POS-1", 10, "bag", D("2.5"), False, "v1")}},
            "MAPPING_NOT_CONFIRMED",
        ),
        (
            {"mappings": {"POS-1": ConfirmedMapping("POS-1", 10, "bag", D("2.5"), True, "v2")}},
            "MAPPING_CHANGED",
        ),
        (
            {"mappings": {"POS-1": ConfirmedMapping("POS-1", 11, "bag", D("2.5"), True, "v1")}},
            "MAPPING_CHANGED",
        ),
        (
            {"mappings": {"POS-1": ConfirmedMapping("POS-1", 10, "pcs", D("2.5"), True, "v1")}},
            "UNIT_MISMATCH",
        ),
        ({"mappings": {"POS-1": ConfirmedMapping("POS-1", 10, "bag", D("2"), True, "v1")}}, "UNIT_MISMATCH"),
        ({"line": OrderLineRef(1, "POS-1", 10, D("101"), "v1")}, "FRACTIONAL_QUANTITY_NOT_ALLOWED"),
        ({"line": OrderLineRef(1, "POS-1", 10, D("0"), "v1")}, "QUANTITY_INVALID"),
        ({"line": OrderLineRef(1, "UNMAPPED", 10, D("100"), "v1")}, "MAPPING_NOT_CONFIRMED"),
    ],
)
def test_reverse_sku_fails_closed(over: dict, code: str) -> None:
    with pytest.raises(ReverseSkuError) as caught:
        _resolve(**over)
    assert caught.value.code == code


def test_two_local_skus_of_one_global_product_are_never_pooled_or_guessed() -> None:
    m = {
        "POS-A": ConfirmedMapping("POS-A", 10, "bag", D("1"), True, "v1"),
        "POS-B": ConfirmedMapping("POS-B", 10, "bag", D("1"), True, "v1"),
    }
    rels = [
        WmsSkuRelation("SE", "WH-1", "POS-A", "W-A", "bag", D("1"), False, True),
        WmsSkuRelation("SE", "WH-1", "POS-B", "W-B", "bag", D("1"), False, True),
    ]
    got = resolve_reservation_lines(
        "SE",
        "WH-1",
        [OrderLineRef(1, "POS-A", 10, D(5), "v1"), OrderLineRef(2, "POS-B", 10, D(7), "v1")],
        m,
        rels,
        {("WH-1", "W-A"), ("WH-1", "W-B")},
    )
    assert [(g.wms_sku, g.quantity) for g in got] == [("W-A", D(5)), ("W-B", D(7))]  # explicit per SKU


def test_non_exact_conversion_is_rejected_not_rounded() -> None:
    with pytest.raises(ReverseSkuError) as caught:
        _resolve(
            mappings={"POS-1": ConfirmedMapping("POS-1", 10, "bag", D("3"), True, "v1")},
            relations=[WmsSkuRelation("SE", "WH-1", "POS-1", "W-9", "bag", D("3"), True, True)],
            line=OrderLineRef(1, "POS-1", 10, D("1"), "v1"),
        )
    assert caught.value.code == "QUANTITY_NOT_EXACT"


# --- reserve / recovery ---------------------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


def test_accepted_reservation_is_verified_and_idempotent_key_is_stable() -> None:
    wms = FakeWms({("WH-1", "W-9"): D(100)})
    req = request()
    ack = run(reserve_with_recovery(wms, req))
    assert ack.status == "accepted" and wms.available[("WH-1", "W-9")] == 60
    assert (
        req.idempotency_key == build_request("SE", 1, 5, lines()).idempotency_key
    )  # same for 2nd vehicle/retry
    assert req.idempotency_key != idempotency_key("SE", 1, 6, lines())  # another plan -> another key
    again = run(reserve_with_recovery(wms, req))
    assert again == ack and wms.available[("WH-1", "W-9")] == 60  # no second reservation


def test_wms_reject_and_insufficient_stock_never_confirm() -> None:
    wms = FakeWms({("WH-1", "W-9"): D(10)})
    with pytest.raises(WmsRejected):
        run(reserve_with_recovery(wms, request("40")))
    assert wms.available[("WH-1", "W-9")] == 10


def test_lost_ack_is_recovered_by_status_lookup_never_a_blind_duplicate() -> None:
    wms = FakeWms({("WH-1", "W-9"): D(100)})
    wms.timeout_after_commit = 1
    ack = run(reserve_with_recovery(wms, request()))
    assert ack.status == "accepted" and wms.calls == ["reserve", "status"]
    assert wms.available[("WH-1", "W-9")] == 60


def test_timeout_before_wms_saw_the_request_is_unknown_and_fails_closed() -> None:
    wms = FakeWms({("WH-1", "W-9"): D(100)})
    wms.timeout_before_commit = 1
    with pytest.raises(ReservationUnknown):
        run(reserve_with_recovery(wms, request(), status_attempts=2))
    assert wms.calls.count("reserve") == 1  # no blind retry of reserve
    assert wms.available[("WH-1", "W-9")] == 100


def test_status_lookup_that_keeps_failing_is_unknown() -> None:
    wms = FakeWms({("WH-1", "W-9"): D(100)})
    wms.timeout_after_commit, wms.status_timeouts = 1, 5
    with pytest.raises(ReservationUnknown):
        run(reserve_with_recovery(wms, request(), status_attempts=3))


def test_partial_or_mismatched_ack_is_compensated_and_rejected() -> None:
    for mode in ("partial", "wrong_sku"):
        wms = FakeWms({("WH-1", "W-9"): D(100)})
        wms.mode = mode
        with pytest.raises(ReservationMismatch):
            run(reserve_with_recovery(wms, request()))
        assert "release" in wms.calls  # compensating release of what WMS holds


def test_concurrent_reservations_cannot_oversell() -> None:
    wms = FakeWms({("WH-1", "W-9"): D(50)})
    first, second = build_request("SE", 1, 5, lines("40")), build_request("SE", 2, 6, lines("40"))

    async def both():
        return await asyncio.gather(
            reserve_with_recovery(wms, first), reserve_with_recovery(wms, second), return_exceptions=True
        )

    results = run(both())
    assert sum(isinstance(r, ReservationAck) for r in results) == 1
    assert sum(isinstance(r, WmsRejected) for r in results) == 1
    assert wms.available[("WH-1", "W-9")] == 10


def test_default_port_is_disabled_so_no_write_can_reach_a_real_wms() -> None:
    with pytest.raises(WmsDisabled):
        run(reserve_with_recovery(DisabledWmsPort(), request()))


# --- no double subtraction ---------------------------------------------------------------------------


def test_reservation_lowers_available_not_on_hand_and_is_not_subtracted_twice() -> None:
    key = ("WH-1", "W-9")
    commitment = CfoCommitment("WH-1", "W-9", D(60), "wms_acked", reflected_in_batch_id=12)
    lag = compute_availability(11, {key: (D(100), D(0))}, [commitment], [key])[key]
    assert (lag.wms_available, lag.pending_subtracted, lag.available, lag.pending_inclusion) == (
        100,
        60,
        40,
        True,
    )
    done = compute_availability(12, {key: (D(100), D(60))}, [commitment], [key])[key]
    assert (done.on_hand, done.wms_available, done.pending_subtracted, done.available) == (100, 40, 0, 40)
    assert done.pending_inclusion is False


def test_later_as_of_without_a_version_proof_does_not_lift_the_protection() -> None:
    key = ("WH-1", "W-9")
    no_proof = CfoCommitment("WH-1", "W-9", D(60), "wms_acked", reflected_in_batch_id=None)
    got = compute_availability(99, {key: (D(100), D(60))}, [no_proof], [key])[key]
    assert got.pending_subtracted == 60 and got.pending_inclusion is True  # conservative, flagged


def test_tentative_hold_is_subtracted_other_channel_reserve_is_not_ours_and_missing_row_is_unknown() -> None:
    key = ("WH-1", "W-9")
    tentative = CfoCommitment("WH-1", "W-9", D(10), "tentative")
    got = compute_availability(5, {key: (D(100), D(30))}, [tentative], [key])[
        key
    ]  # 30 reserved by other channels
    assert (got.wms_available, got.available) == (70, 60)
    short = compute_availability(5, {key: (D(5), D(0))}, [tentative], [key])[key]
    assert short.available == 0 and short.shortfall is True
    with pytest.raises(ValueError, match="STOCK_ROW_UNKNOWN"):
        compute_availability(5, {}, [], [key])


# --- immediate refresh after ACK ---------------------------------------------------------------------


def snapshot(batch: int) -> StockSnapshotDTO:
    items = (StockItemDTO("WH-1", "W-9", D(100), D(60)),)
    return StockSnapshotDTO(datetime(2026, 11, 9, 12, batch % 60, tzinfo=UTC), items, batch, len(items))


def ack(reflected: int | None = 12) -> ReservationAck:
    return ReservationAck("R-1", "accepted", (), "7", reflected)


def test_refresh_returns_as_soon_as_the_batch_proves_inclusion() -> None:
    batches = iter([snapshot(11), snapshot(12)])

    async def fetch():
        return next(batches)

    got = run(refresh_after_ack(fetch, ack(), validate=lambda s: None, known_batch_id=11))
    assert got.included is True and got.snapshot.batch_id == 12 and got.attempts == 2


def test_refresh_that_lags_keeps_the_protection_and_a_partial_batch_is_never_accepted() -> None:
    async def lagging():
        return snapshot(11)

    got = run(refresh_after_ack(lagging, ack(), validate=lambda s: None, attempts=2))
    assert got.included is False and got.snapshot.batch_id == 11

    def reject(_s):
        raise ValueError("partial batch")

    with pytest.raises(StockRefreshFailed):
        run(refresh_after_ack(lagging, ack(), validate=reject, attempts=2))

    async def unavailable():
        raise WmsUnavailable()

    with pytest.raises(StockRefreshFailed):
        run(refresh_after_ack(unavailable, ack(), validate=lambda s: None, attempts=2))


def test_refresh_never_goes_back_to_an_older_batch_and_no_proof_means_not_included() -> None:
    async def older():
        return snapshot(10)

    with pytest.raises(StockRefreshFailed):
        run(refresh_after_ack(older, ack(), validate=lambda s: None, known_batch_id=11, attempts=2))

    async def newest():
        return snapshot(50)

    got = run(refresh_after_ack(newest, ack(None), validate=lambda s: None, attempts=1))
    assert got.included is False  # newer batch id without a WMS inclusion proof is not proof
