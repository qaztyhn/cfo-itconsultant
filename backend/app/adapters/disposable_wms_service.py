"""Isolated synthetic WMS HTTP contract: SQLite-durable reserve/status/release and signed batches.

NOT a production WMS adapter, an approval service, or a CFO stock publisher.
Nothing is mounted in normal backend routes. Explicit disposable settings are mandatory.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

FROZEN = "2026-11-04T10:05:00+01:00"
E0_04_FROZEN = "2026-12-01T10:05:00+01:00"
ALLOWED_CLOCKS = frozenset({FROZEN, E0_04_FROZEN})


def permitted() -> bool:
    return (
        os.environ.get("APP_ENV") == "test"
        and os.environ.get("DEMO_DISPOSABLE") == "1"
        and os.environ.get("APP_NOW") in ALLOWED_CLOCKS
        and os.environ.get("WMS_RESERVATION_MODE") == "simulated"
        and os.environ.get("WMS_PRODUCTION_ENABLED", "0").lower() in ("", "0", "false")
    )


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def decimal(value: str, *, positive: bool = False) -> Decimal:
    try:
        d = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError("QUANTITY_INVALID") from None
    if not d.is_finite() or d < 0 or (positive and d == 0) or d.as_tuple().exponent < -3:
        raise ValueError("QUANTITY_INVALID")
    return d


def number(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.001")), "f")


class NativeLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_line_id: int = Field(gt=0)
    pos_sku: str = Field(min_length=1)
    wms_sku: str = Field(min_length=1)
    warehouse_code: str = Field(min_length=1)
    wms_unit: str = Field(min_length=1)
    mapping_version: str = Field(min_length=1)
    quantity: str = Field(min_length=1)


class Reserve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str
    order_id: int = Field(gt=0)
    plan_id: int = Field(gt=0)
    source_version: int = Field(gt=0)
    source_ref: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    lines: list[NativeLine] = Field(min_length=1)


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str
    reservation_id: str
    idempotency_key: str


def _error(code: str, status: int = 409) -> None:
    raise HTTPException(status_code=status, detail=code)


def _seed(conn: sqlite3.Connection, fixture: dict[str, Any]) -> None:
    if fixture.get("source_kind") != "synthetic_demo" or fixture.get("market") != "SE":
        raise ValueError("Synthetic Swedish fixture required")
    rows, mapping = fixture.get("stock"), fixture.get("mapping")
    source_orders = fixture.get("source_orders")
    if (
        not isinstance(rows, list)
        or not rows
        or not isinstance(mapping, list)
        or not mapping
        or not isinstance(source_orders, list)
        or not source_orders
    ):
        raise ValueError("Explicit stock rows and native SKU mappings required")
    fingerprint = hashlib.sha256(canonical(fixture)).hexdigest()
    prior = conn.execute("SELECT value FROM meta WHERE key='fixture_hash'").fetchone()
    if prior:
        if prior[0] != fingerprint:
            raise ValueError("Existing synthetic database cannot be reseeded with changed provenance")
        return
    seen_rows: set[tuple[str, str]] = set()
    for item in rows:
        wh, sku, unit = (item.get(k) for k in ("warehouse_code", "wms_sku", "wms_unit"))
        if not all(isinstance(v, str) and v.strip() for v in (wh, sku, unit)):
            raise ValueError("Invalid synthetic WMS stock identity")
        key = (wh, sku)
        if key in seen_rows:
            raise ValueError("Duplicate synthetic stock key")
        seen_rows.add(key)
        qty = decimal(item.get("on_hand"))
        conn.execute(
            "INSERT INTO stock(warehouse,sku,unit,on_hand,reserved) VALUES(?,?,?,?,?)",
            (wh, sku, unit, number(qty), number(Decimal(0))),
        )
    seen_mapping: set[tuple[str, str, str]] = set()
    for item in mapping:
        market, wh, pos = (item.get(k) for k in ("market", "warehouse_code", "pos_sku"))
        sku, unit, version = (item.get(k) for k in ("wms_sku", "wms_unit", "mapping_version"))
        if not all(isinstance(v, str) and v.strip() for v in (market, wh, pos, sku, unit, version)):
            raise ValueError("Missing confirmed mapping provenance")
        if item.get("confirmed") is not True or market != "SE":
            raise ValueError("Synthetic relation must be explicitly confirmed and market scoped")
        if (wh, sku) not in seen_rows:
            raise ValueError("Mapped SKU is absent from the declared warehouse inventory")
        unit_row = conn.execute("SELECT unit FROM stock WHERE warehouse=? AND sku=?", (wh, sku)).fetchone()
        if unit_row[0] != unit:
            raise ValueError("WMS stock unit does not match confirmed relation")
        key = (market, wh, pos)
        if key in seen_mapping:
            raise ValueError("Ambiguous POS to WMS native SKU relation")
        seen_mapping.add(key)
        conn.execute(
            "INSERT INTO mapping(market,warehouse,pos_sku,wms_sku,unit,version) VALUES(?,?,?,?,?,?)",
            (market, wh, pos, sku, unit, version),
        )
    seen_lines: set[tuple[int, int]] = set()
    for order in source_orders:
        order_id, plan_id, version = (
            order.get("order_id"),
            order.get("plan_id"),
            order.get("source_version"),
        )
        source_ref = order.get("source_ref")
        source_lines = order.get("lines")
        if (
            type(order_id) is not int
            or order_id <= 0
            or type(plan_id) is not int
            or plan_id <= 0
            or type(version) is not int
            or version <= 0
            or not isinstance(source_ref, str)
            or not source_ref
            or not isinstance(source_lines, list)
            or not source_lines
        ):
            raise ValueError("Explicit synthetic Source order/version evidence required")
        for line in source_lines:
            line_id = line.get("order_line_id")
            pos_sku = line.get("pos_sku")
            wh = line.get("warehouse_code")
            quantity = decimal(line.get("quantity"), positive=True)
            if (
                type(line_id) is not int
                or line_id <= 0
                or not isinstance(pos_sku, str)
                or not pos_sku
                or not isinstance(wh, str)
                or not wh
                or (order_id, line_id) in seen_lines
                or ("SE", wh, pos_sku) not in seen_mapping
            ):
                raise ValueError("Synthetic Source line lacks original warehouse/SKU identity")
            seen_lines.add((order_id, line_id))
            conn.execute(
                "INSERT INTO source_lines VALUES(?,?,?,?,?,?,?,?)",
                (
                    order_id,
                    plan_id,
                    version,
                    source_ref,
                    line_id,
                    wh,
                    pos_sku,
                    number(quantity),
                ),
            )
    conn.execute("INSERT INTO meta(key,value) VALUES('fixture_hash',?)", (fingerprint,))
    conn.execute("INSERT INTO meta(key,value) VALUES('batch_id','1')")


def create_app(db_path: Path, api_key: str, fixture: dict[str, Any]) -> FastAPI:
    """Create only a loopback/disposable simulator, never auto-register in CFO."""
    if not permitted() or not api_key or len(api_key) < 24:
        raise RuntimeError("Disposable WMS test mode and private API key required")
    if not str(db_path) or str(db_path) == ":memory:":
        raise RuntimeError("Durable, persistent SQLite file required")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Synthetic WMS ONLY - not a production interface")

    @contextmanager
    def transaction() -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    with transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stock(
            warehouse TEXT NOT NULL,sku TEXT NOT NULL,unit TEXT NOT NULL,
            on_hand TEXT NOT NULL,reserved TEXT NOT NULL,
            PRIMARY KEY(warehouse,sku));
        CREATE TABLE IF NOT EXISTS mapping(
            market TEXT NOT NULL,warehouse TEXT NOT NULL,pos_sku TEXT NOT NULL,
            wms_sku TEXT NOT NULL,unit TEXT NOT NULL,version TEXT NOT NULL,
            PRIMARY KEY(market,warehouse,pos_sku));
        CREATE TABLE IF NOT EXISTS source_lines(
            order_id INTEGER NOT NULL, plan_id INTEGER NOT NULL, source_version INTEGER NOT NULL,
            source_ref TEXT NOT NULL, order_line_id INTEGER NOT NULL, warehouse TEXT NOT NULL,
            pos_sku TEXT NOT NULL, quantity TEXT NOT NULL,
            PRIMARY KEY(order_id,order_line_id));
        CREATE TABLE IF NOT EXISTS reservations(
            request_key TEXT PRIMARY KEY, market TEXT NOT NULL,
            reservation_id TEXT NOT NULL UNIQUE,digest TEXT NOT NULL,
            status TEXT NOT NULL,source_version INTEGER NOT NULL,
            ack TEXT NOT NULL,lines TEXT NOT NULL);
        """)
        # executescript commits the schema DDL; restart a real transaction so an
        # invalid/partial seed can never survive a failed initialization.
        conn.execute("BEGIN IMMEDIATE")
        _seed(conn, fixture)

    def authorize(x_demo_wms_key: str | None) -> None:
        if not permitted():
            _error("DISPOSABLE_WMS_DISABLED", 503)
        if x_demo_wms_key is None or not hmac.compare_digest(x_demo_wms_key, api_key):
            _error("AUTH_INVALID", 401)

    def bump(conn: sqlite3.Connection) -> int:
        value = int(conn.execute("SELECT value FROM meta WHERE key='batch_id'").fetchone()[0]) + 1
        conn.execute("UPDATE meta SET value=? WHERE key='batch_id'", (str(value),))
        return value

    def response(conn: sqlite3.Connection, reservation_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
        if row is None:
            _error("RESERVATION_NOT_FOUND", 404)
        return json.loads(row["ack"])

    @app.post("/v1/reserve")
    def reserve(body: Reserve, x_demo_wms_key: str | None = Header(default=None)) -> dict[str, Any]:
        authorize(x_demo_wms_key)
        if body.market != "SE" or len({x.order_line_id for x in body.lines}) != len(body.lines):
            _error("RESERVATION_SCOPE_INVALID")
        payload = body.model_dump()
        digest = hashlib.sha256(canonical(payload)).hexdigest()
        with transaction() as conn:
            prior = conn.execute(
                "SELECT digest,ack FROM reservations WHERE request_key=?",
                (body.idempotency_key,),
            ).fetchone()
            if prior:
                if prior["digest"] != digest:
                    _error("IDEMPOTENCY_CONFLICT")
                return json.loads(prior["ack"])
            original_lines = conn.execute(
                "SELECT * FROM source_lines WHERE order_id=? ORDER BY order_line_id",
                (body.order_id,),
            ).fetchall()
            if len(original_lines) != len(body.lines) or not original_lines:
                _error("SOURCE_PROVENANCE_UNVERIFIED")
            originals = {int(row["order_line_id"]): row for row in original_lines}
            wanted: dict[tuple[str, str], Decimal] = {}
            lines: list[dict[str, Any]] = []
            for line in body.lines:
                match = conn.execute(
                    "SELECT wms_sku,unit,version FROM mapping WHERE market=? AND warehouse=? AND pos_sku=?",
                    (body.market, line.warehouse_code, line.pos_sku),
                ).fetchone()
                if (
                    match is None
                    or match["wms_sku"] != line.wms_sku
                    or match["unit"] != line.wms_unit
                    or match["version"] != line.mapping_version
                ):
                    _error("NATIVE_MAPPING_UNVERIFIED")
                try:
                    quantity = decimal(line.quantity, positive=True)
                except ValueError:
                    _error("QUANTITY_INVALID", 422)
                original = originals.get(line.order_line_id)
                if (
                    original is None
                    or original["plan_id"] != body.plan_id
                    or original["source_version"] != body.source_version
                    or original["source_ref"] != body.source_ref
                    or original["warehouse"] != line.warehouse_code
                    or original["pos_sku"] != line.pos_sku
                    or original["quantity"] != number(quantity)
                ):
                    _error("SOURCE_PROVENANCE_UNVERIFIED")
                key = (line.warehouse_code, line.wms_sku)
                wanted[key] = wanted.get(key, Decimal(0)) + quantity
                lines.append(
                    {
                        "order_line_id": line.order_line_id,
                        "pos_sku": line.pos_sku,
                        "wms_sku": line.wms_sku,
                        "warehouse_code": line.warehouse_code,
                        "wms_unit": line.wms_unit,
                        "mapping_version": line.mapping_version,
                        "quantity": number(quantity),
                    }
                )
            for (wh, sku), qty in wanted.items():
                stock = conn.execute(
                    "SELECT on_hand,reserved FROM stock WHERE warehouse=? AND sku=?",
                    (wh, sku),
                ).fetchone()
                if stock is None or Decimal(stock["on_hand"]) - Decimal(stock["reserved"]) < qty:
                    _error("WMS_INSUFFICIENT_STOCK")
            for (wh, sku), qty in wanted.items():
                conn.execute(
                    "UPDATE stock SET reserved=? WHERE warehouse=? AND sku=?",
                    (
                        number(
                            Decimal(
                                conn.execute(
                                    "SELECT reserved FROM stock WHERE warehouse=? AND sku=?",
                                    (wh, sku),
                                ).fetchone()[0]
                            )
                            + qty
                        ),
                        wh,
                        sku,
                    ),
                )
            batch = bump(conn)
            reservation_id = "SYN-" + digest[:24]
            ack = {
                "source_kind": "synthetic_demo",
                "market": body.market,
                "idempotency_key": body.idempotency_key,
                "reservation_id": reservation_id,
                "status": "accepted",
                "revision": f"synthetic:{batch}",
                "reflected_in_batch_id": batch,
                "source_version": body.source_version,
                "source_ref": body.source_ref,
                "lines": lines,
            }
            conn.execute(
                "INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?)",
                (
                    body.idempotency_key,
                    body.market,
                    reservation_id,
                    digest,
                    "accepted",
                    body.source_version,
                    canonical(ack).decode(),
                    canonical(lines).decode(),
                ),
            )
            return ack

    @app.get("/v1/status/{market}/{request_key}")
    def status(
        market: str, request_key: str, x_demo_wms_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        authorize(x_demo_wms_key)
        with transaction() as conn:
            row = conn.execute(
                "SELECT ack FROM reservations WHERE market=? AND request_key=?",
                (market, request_key),
            ).fetchone()
            if row is None:
                _error("RESERVATION_NOT_FOUND", 404)
            return json.loads(row[0])

    @app.post("/v1/release")
    def release(body: Release, x_demo_wms_key: str | None = Header(default=None)) -> dict[str, Any]:
        authorize(x_demo_wms_key)
        with transaction() as conn:
            row = conn.execute(
                "SELECT * FROM reservations WHERE reservation_id=? AND market=?",
                (body.reservation_id, body.market),
            ).fetchone()
            if row is None:
                _error("RESERVATION_NOT_FOUND", 404)
            if body.idempotency_key != row["request_key"] + ":release":
                _error("RELEASE_KEY_CONFLICT")
            if row["status"] == "released":
                return json.loads(row["ack"])
            for line in json.loads(row["lines"]):
                stock = conn.execute(
                    "SELECT reserved FROM stock WHERE warehouse=? AND sku=?",
                    (line["warehouse_code"], line["wms_sku"]),
                ).fetchone()
                if stock is None or Decimal(stock[0]) < Decimal(line["quantity"]):
                    _error("RESERVATION_STATE_CONFLICT")
                conn.execute(
                    "UPDATE stock SET reserved=? WHERE warehouse=? AND sku=?",
                    (
                        number(Decimal(stock[0]) - Decimal(line["quantity"])),
                        line["warehouse_code"],
                        line["wms_sku"],
                    ),
                )
            batch = bump(conn)
            ack = json.loads(row["ack"])
            ack.update(
                {
                    "status": "released",
                    "revision": f"synthetic:{batch}",
                    "reflected_in_batch_id": batch,
                }
            )
            conn.execute(
                "UPDATE reservations SET status='released',ack=? WHERE request_key=?",
                (canonical(ack).decode(), row["request_key"]),
            )
            return ack

    @app.get("/v1/stock")
    def stock(x_demo_wms_key: str | None = Header(default=None)) -> dict[str, Any]:
        authorize(x_demo_wms_key)
        with transaction() as conn:
            rows = conn.execute("SELECT * FROM stock ORDER BY warehouse,sku").fetchall()
            batch = int(conn.execute("SELECT value FROM meta WHERE key='batch_id'").fetchone()[0])
            included = sorted(
                row[0]
                for row in conn.execute(
                    "SELECT reservation_id FROM reservations WHERE status='accepted'"
                ).fetchall()
            )
            payload = {
                "source_kind": "synthetic_demo",
                "market": "SE",
                "as_of": os.environ["APP_NOW"],
                "batch_id": batch,
                "complete": True,
                "item_count": len(rows),
                "included_reservation_ids": included,
                "items": [
                    {
                        "warehouse_code": row["warehouse"],
                        "wms_sku": row["sku"],
                        "wms_unit": row["unit"],
                        "on_hand": row["on_hand"],
                        "reserved": row["reserved"],
                    }
                    for row in rows
                ],
            }
            payload["sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
            payload["hmac_sha256"] = hmac.new(
                api_key.encode(), canonical(payload), hashlib.sha256
            ).hexdigest()
            return payload

    return app


def verify_batch(batch: dict[str, Any], shared_key: str, *, expected_reservation_id: str) -> bool:
    """Require complete signed synthetic batch and explicit reservation inclusion."""
    try:
        content = {key: value for key, value in batch.items() if key not in ("sha256", "hmac_sha256")}
        digest = hashlib.sha256(canonical(content)).hexdigest()
        signed = {**content, "sha256": digest}
        if not hmac.compare_digest(batch["sha256"], digest):
            return False
        if not hmac.compare_digest(
            batch["hmac_sha256"],
            hmac.new(shared_key.encode(), canonical(signed), hashlib.sha256).hexdigest(),
        ):
            return False
        items = batch["items"]
        if (
            batch["source_kind"] != "synthetic_demo"
            or batch["market"] != "SE"
            or batch["complete"] is not True
            or batch["item_count"] != len(items)
            or batch["as_of"] not in ALLOWED_CLOCKS
            or type(batch["batch_id"]) is not int
            or batch["batch_id"] < 1
            or expected_reservation_id not in batch["included_reservation_ids"]
        ):
            return False
        if len({(r["warehouse_code"], r["wms_sku"]) for r in items}) != len(items):
            return False
        for row in items:
            if decimal(row["reserved"]) > decimal(row["on_hand"]):
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


if __name__ == "__main__":
    import uvicorn

    key = os.environ.get("SYNTHETIC_WMS_API_KEY", "")
    db = Path(os.environ.get("SYNTHETIC_WMS_DB", ""))
    spec = Path(os.environ.get("SYNTHETIC_WMS_FIXTURE", ""))
    if not permitted() or not key or not db.is_absolute() or not spec.is_file():
        raise SystemExit("BLOCKED: test-only synthetic WMS configuration required")
    app = create_app(db, key, json.loads(spec.read_text(encoding="utf-8")))
    uvicorn.run(app, host="127.0.0.1", port=8188)
