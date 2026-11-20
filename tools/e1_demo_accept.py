"""Run the E1 approval against the isolated E0-04 PostgreSQL scenario.

Requires the private E0-04 environment in the process, migration head, and
DEMO_D7_FIXTURE_DIR. Creates only a disposable WMS fixture/SQLite file.
"""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.core.security import issue_token
from app.main import app
from app.services.auth_service import load_active_profile
from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
REF = "SE-2026-000249"
NOW = "2026-12-01T10:05:00+01:00"


async def scenario() -> dict[str, object]:
    async with get_sessionmaker()() as db:
        row = (
            await db.execute(
                text(
                    "SELECT o.id, p.id, o.source_version, l.id, l.local_sku, "
                    "l.qty_base, o.status, p.status, w.code "
                    "FROM ops.customer_order o "
                    "JOIN plan.fulfilment_plan p ON p.order_id=o.id "
                    "JOIN ops.order_line l ON l.order_id=o.id "
                    "JOIN ref.location w ON w.id=p.warehouse_id "
                    "WHERE o.external_ref=:ref AND o.status='PLANNED' "
                    "AND p.rank=1 AND p.status='proposed' AND p.run_id=("
                    "SELECT r.id FROM plan.planning_run r WHERE r.order_id=o.id "
                    "ORDER BY r.run_no DESC,r.id DESC LIMIT 1)"
                ),
                {"ref": REF},
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("The latest E0-04 run has no proposed rank-1 plan")
        profile = await load_active_profile(db, 1)
        data = {
            "order_id": row[0],
            "plan_id": row[1],
            "source_version": row[2],
            "line_id": row[3],
            "sku": row[4],
            "quantity": str(row[5]),
            "order_status": row[6],
            "plan_status": row[7],
            "warehouse": row[8],
            "profile": profile,
        }
    await get_engine().dispose()
    return data


def fixture(data: dict[str, object]) -> dict[str, object]:
    if (
        data["source_version"] != 1
        or data["sku"] != "SE-BRD-GYP-13"
        or data["warehouse"] != "STO"
    ):
        raise RuntimeError("E0-04 fixed scenario differs from the reviewed order")
    profile = data["profile"]
    if "dispatcher" not in profile.roles or profile.market != "SE":
        raise RuntimeError("The selected actor is not the SE Dispatcher")
    native = "WMS-BRD-GYP-13"
    stock = [
        {
            "warehouse_code": wh,
            "wms_sku": native,
            "wms_unit": "piece",
            "on_hand": "5000.000",
        }
        for wh in ("GBG", "STO", "MLM")
    ]
    mapping = [
        {
            "market": "SE",
            "warehouse_code": wh,
            "pos_sku": data["sku"],
            "wms_sku": native,
            "wms_unit": "piece",
            "mapping_version": "e1:confirmed-v1",
            "confirmed": True,
        }
        for wh in ("GBG", "STO", "MLM")
    ]
    return {
        "source_kind": "synthetic_demo",
        "market": "SE",
        "stock": stock,
        "mapping": mapping,
        "source_orders": [
            {
                "order_id": data["order_id"],
                "plan_id": data["plan_id"],
                "source_version": data["source_version"],
                "source_ref": REF,
                "lines": [
                    {
                        "order_line_id": data["line_id"],
                        "pos_sku": data["sku"],
                        "warehouse_code": "STO",
                        "quantity": data["quantity"],
                    }
                ],
            }
        ],
    }


async def evidence(plan_id: int) -> dict[str, object]:
    async with get_sessionmaker()() as db:
        result = await db.execute(
            text(
                "SELECT o.status, p.status, i.reservation_id, i.reflected_in_batch_id, "
                "i.stock_write_run_id, w.source_kind, w.source_batch_id, w.ingest_run_id, "
                "(SELECT count(*) FROM ops.delivery_trip t JOIN plan.plan_vehicle v "
                "ON v.id=t.plan_vehicle_id WHERE v.plan_id=p.id), "
                "(SELECT count(*) FROM audit.decision_log d WHERE d.action='PLAN_APPROVED' AND d.order_id=o.id), "
                "(SELECT count(*) FROM ops.notification n WHERE n.order_id=o.id AND n.template='CONFIRMED') "
                "FROM ops.customer_order o JOIN plan.fulfilment_plan p ON p.id=o.approved_plan_id "
                "LEFT JOIN ops.wms_reservation_intent i ON i.order_id=o.id AND i.plan_id=p.id "
                "LEFT JOIN ops.stock_write_run w ON w.id=i.stock_write_run_id "
                "WHERE o.external_ref=:ref AND p.id=:plan_id"
            ),
            {"ref": REF, "plan_id": plan_id},
        )
        row = result.one()
        data = dict(
            zip(
                (
                    "order_status",
                    "plan_status",
                    "reservation_id",
                    "reflected_batch",
                    "stock_write_run_id",
                    "stock_origin",
                    "stock_batch",
                    "ingest_run_id",
                    "trip_count",
                    "audit_count",
                    "confirmed_count",
                ),
                row,
                strict=True,
            )
        )
    await get_engine().dispose()
    return data


def main() -> int:
    settings = get_settings()
    if (settings.app_env, settings.app_now, settings.wms_reservation_mode) != (
        "test",
        NOW,
        "simulated",
    ):
        raise RuntimeError(
            "E1 requires the fixed disposable test clock and explicit WMS mode"
        )
    if os.getenv("DEMO_DISPOSABLE") != "1" or not settings.synthetic_wms_api_key:
        raise RuntimeError("Disposable WMS and private key required")
    if settings.synthetic_wms_api_key != settings.synthetic_wms_shared_key:
        raise RuntimeError("Disposable signing and client keys must match")
    data = asyncio.run(scenario())
    path = Path(os.environ["SYNTHETIC_WMS_FIXTURE"])
    path.write_text(json.dumps(fixture(data), indent=2), encoding="utf-8")
    command = [sys.executable, "-m", "app.adapters.disposable_wms_service"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    worker = subprocess.Popen(
        command,
        cwd=ROOT / "backend",
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    try:
        for _ in range(50):
            if worker.poll() is not None:
                raise RuntimeError("Disposable WMS failed to start")
            try:
                response = httpx.get(
                    settings.synthetic_wms_url + "/openapi.json", timeout=1
                )
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Disposable WMS did not become ready")
        token = issue_token(data["profile"].id, data["profile"].claims())
        with TestClient(app) as client:
            headers = {
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"e1-demo-order-249-plan-{data['plan_id']}",
            }
            first = client.post(
                f"/api/v1/plans/{data['plan_id']}/approve", headers=headers, json={}
            )
            second = client.post(
                f"/api/v1/plans/{data['plan_id']}/approve", headers=headers, json={}
            )
            client.portal.call(get_engine().dispose)
        get_sessionmaker.cache_clear()
        get_engine.cache_clear()
        before = {
            "first_http": first.status_code,
            "second_http": second.status_code,
            "first": first.json(),
            "second": second.json(),
        }
        assert first.status_code == second.status_code == 200, before
        assert first.json() == second.json()
        assert len(first.json()["trip_ids"]) == 1
        proven = asyncio.run(evidence(data["plan_id"]))
        with sqlite3.connect(os.environ["SYNTHETIC_WMS_DB"]) as wms:
            proven["wms_reservation_count"] = wms.execute(
                "SELECT count(*) FROM reservations"
            ).fetchone()[0]
        print(json.dumps(before, default=str))
        print(json.dumps(proven, default=str))
        assert proven["order_status"] == "APPROVED"
        assert proven["stock_origin"] == "wms_synthetic"
        assert proven["stock_batch"] == proven["reflected_batch"] == 2
        assert (
            proven["trip_count"]
            == proven["audit_count"]
            == proven["confirmed_count"]
            == 1
        )
        assert proven["wms_reservation_count"] == 1
        return 0
    finally:
        worker.terminate()
        worker.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
