"""Build an E1 synthetic WMS fixture from a proposed disposable demo plan.

Used only after the browser has clicked Sales Sync + Check feasibility.
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

CLOCK = "2026-12-01T10:05:00+01:00"
E0_PROJECT = "cfo-demo-e004"
T26_PROJECT = "cfo-demo-t26"


def stock_units(base_quantity: Decimal, factor: Decimal) -> Decimal:
    if factor <= 0:
        raise ValueError("Confirmed stock unit has an invalid conversion factor")
    units = base_quantity / factor
    rounded = units.quantize(Decimal("0.001"))
    if rounded * factor != base_quantity:
        raise ValueError("Existing quantity cannot be represented exactly in WMS units")
    return rounded


async def t26_fixture(source_ref: str, plan_id: int, rank: int) -> dict[str, object]:
    from app.core.db import get_engine, get_sessionmaker
    from app.services.stock_scope_service import scope_effective_at

    try:
        async with get_sessionmaker()() as db, db.begin():
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            plan = (
                (
                    await db.execute(
                        text("""
                        SELECT o.id AS order_id, o.source_version, o.market_id,
                               p.warehouse_id, w.code AS warehouse
                        FROM plan.fulfilment_plan p
                        JOIN ops.customer_order o ON o.id = p.order_id
                        JOIN ref.market m ON m.id = o.market_id
                        JOIN ref.location w ON w.id = p.warehouse_id AND w.market_id = m.id
                        WHERE p.id = :plan_id AND p.rank = :rank AND p.status = 'proposed'
                          AND o.external_ref = :source_ref AND o.status = 'PLANNED'
                          AND m.code = 'SE' AND p.run_id = (
                              SELECT r.id FROM plan.planning_run r WHERE r.order_id = o.id
                              ORDER BY r.run_no DESC, r.id DESC LIMIT 1
                          )
                    """),
                        {"plan_id": plan_id, "rank": rank, "source_ref": source_ref},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if plan is None:
                raise ValueError("Source ref, plan ID and rank must match a current proposed T26 plan")

            active = await db.scalar(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM ops.wms_reservation_intent
                        WHERE market_id = :market_id AND status NOT IN ('released', 'rejected')
                    )
                """),
                {"market_id": plan["market_id"]},
            )
            if active:
                raise ValueError("This market already has a WMS intent that requires its existing simulator")

            now = datetime.fromisoformat(CLOCK)
            scope = await scope_effective_at(db, plan["market_id"], now)
            stock_run = (
                (
                    await db.execute(
                        text("""
                        SELECT scope_version_id, ingest_run_id, source_kind
                        FROM ops.stock_write_run
                        WHERE market_id = :market_id AND status = 'accepted' AND as_of <= :now
                        ORDER BY as_of DESC, id DESC LIMIT 1
                    """),
                        {"market_id": plan["market_id"], "now": now},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if scope is None or stock_run is None or stock_run["scope_version_id"] != scope.id:
                raise ValueError("The current stock scope must have a complete accepted snapshot")
            if stock_run["source_kind"] != "source":
                raise ValueError("The current snapshot requires the existing synthetic WMS ledger")

            balances = (
                (
                    await db.execute(
                        text("""
                        SELECT w.id AS warehouse_id, w.code AS warehouse, p.local_sku,
                               p.global_product_id, p.sale_unit, p.units_to_base,
                               s.on_hand, s.wms_reserved
                        FROM ops.stock_snapshot s
                        JOIN ref.location w ON w.id = s.warehouse_id
                        JOIN ref.product_se p ON p.global_product_id = s.global_product_id
                        WHERE w.id = ANY(:warehouses) AND p.local_sku = ANY(:skus)
                          AND w.market_id = :market_id AND p.mapping_status = 'confirmed'
                          AND s.run_id = :run_id
                        ORDER BY w.code, p.local_sku
                    """),
                        {
                            "warehouses": scope.warehouse_ids,
                            "skus": scope.skus,
                            "market_id": plan["market_id"],
                            "run_id": stock_run["ingest_run_id"],
                        },
                    )
                )
                .mappings()
                .all()
            )
            expected = {(wid, sku) for wid in scope.warehouse_ids for sku in scope.skus}
            if {(row["warehouse_id"], row["local_sku"]) for row in balances} != expected:
                raise ValueError("The accepted snapshot is missing a scoped warehouse/SKU")
            if len({row["global_product_id"] for row in balances}) != len(scope.skus):
                raise ValueError("The normalized snapshot cannot recover stock per aliased POS SKU")

            lines = (
                (
                    await db.execute(
                        text("""
                        SELECT id, local_sku, global_product_id, qty_sale, qty_base
                        FROM ops.order_line WHERE order_id = :order_id ORDER BY id
                    """),
                        {"order_id": plan["order_id"]},
                    )
                )
                .mappings()
                .all()
            )
    finally:
        await get_engine().dispose()

    stock = []
    mapping = []
    by_identity = {(row["warehouse_id"], row["local_sku"]): row for row in balances}
    for row in balances:
        # The simulator owns a distinct native SKU namespace for this synthetic,
        # one-to-one dataset. The POS SKU and unit come from the live catalogue.
        identity = {
            "warehouse_code": row["warehouse"],
            "wms_sku": f"WMS-{row['local_sku']}",
            "wms_unit": row["sale_unit"],
        }
        if row["wms_reserved"] != 0:
            raise ValueError("Nonzero existing WMS reserves require the original simulator ledger")
        on_hand = stock_units(row["on_hand"], row["units_to_base"])
        stock.append({**identity, "on_hand": str(on_hand)})
        mapping.append(
            {
                **identity,
                "market": "SE",
                "pos_sku": row["local_sku"],
                "mapping_version": f"t26:scope-{scope.version}",
                "confirmed": True,
            }
        )

    source_lines = []
    for line in lines:
        mapped = by_identity.get((plan["warehouse_id"], line["local_sku"]))
        if (
            mapped is None
            or mapped["global_product_id"] != line["global_product_id"]
            or line["qty_base"] is None
        ):
            raise ValueError("A proposed order line lacks matching scoped stock and catalogue evidence")
        quantity = stock_units(line["qty_base"], mapped["units_to_base"])
        if quantity <= 0 or quantity != line["qty_sale"] or quantity != quantity.to_integral_value():
            raise ValueError("An order line cannot be reserved exactly by the synthetic WMS mapping")
        source_lines.append(
            {
                "order_line_id": line["id"],
                "pos_sku": line["local_sku"],
                "warehouse_code": plan["warehouse"],
                "quantity": str(quantity),
            }
        )
    if not source_lines:
        raise ValueError("The proposed T26 order has no lines")
    return {
        "source_kind": "synthetic_demo",
        "market": "SE",
        "stock": stock,
        "mapping": mapping,
        "source_orders": [
            {
                "source_ref": source_ref,
                "order_id": plan["order_id"],
                "plan_id": plan_id,
                "source_version": plan["source_version"],
                "lines": source_lines,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", choices=(E0_PROJECT, T26_PROJECT), default=E0_PROJECT)
    parser.add_argument("--source-ref")
    parser.add_argument("--plan-id", type=int)
    parser.add_argument("--rank", type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    selector = (args.source_ref, args.plan_id, args.rank)
    if args.project == T26_PROJECT:
        if not args.source_ref or not args.plan_id or args.plan_id < 1 or args.rank is None:
            parser.error("T26 requires --source-ref, --plan-id and --rank")
    elif any(value is not None for value in selector):
        parser.error("Plan selection is available only for cfo-demo-t26")
    data = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or os.environ.get("APP_NOW") != CLOCK
    ):
        parser.error("The disposable Planning clock and test gates are required")
    if os.environ.get("COMPOSE_PROJECT_NAME", args.project) != args.project:
        parser.error("The selected demo project does not match COMPOSE_PROJECT_NAME")
    try:
        database = make_url(data.get("DATABASE_URL") or "")
    except (ArgumentError, ValueError):
        parser.error("Private Compose database URL required")
    if (database.host, database.port, database.database) != ("postgres", 5432, "cfo"):
        parser.error("Private Compose database URL required")
    # Same disposable database, host access only. Never rewrite any stock.
    port = os.environ.get("POSTGRES_PORT", data.get("POSTGRES_PORT") or "5432")
    if not port.isdecimal() or not 0 < int(port) <= 65535:
        parser.error("Invalid disposable PostgreSQL port")
    os.environ["DATABASE_URL"] = database.set(host="127.0.0.1", port=int(port)).render_as_string(
        hide_password=False
    )
    try:
        if args.project == T26_PROJECT:
            content = asyncio.run(t26_fixture(*selector))
        else:
            # App settings are cached at import, after selecting the Compose DB port.
            from tools.e1_demo_accept import fixture, scenario

            content = fixture(asyncio.run(scenario()))
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.is_symlink() or args.output.exists():
        parser.error("Use a new private synthetic WMS fixture path")
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(content, stream, indent=2)
    order = content["source_orders"][0]
    print(
        f"E1 fixture PASS: {args.project} {order['source_ref']} "
        f"order_id={order['order_id']} plan_id={order['plan_id']} rank={args.rank or 1} "
        f"proposed; {len(order['lines'])} lines, {len(content['stock'])} stock rows; synthetic only"
    )


if __name__ == "__main__":
    main()
