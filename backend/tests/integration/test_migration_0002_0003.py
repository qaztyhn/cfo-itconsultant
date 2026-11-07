"""Migration 0002_ref + 0003_hr trên PostgreSQL trống: cột khớp 05, cột chung (ASM-001), ràng buộc thật."""

from collections.abc import Iterator

import asyncpg
import pytest

from alembic import command
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.spec05 import COMMON_COLUMNS, spec_tables_in

pytestmark = pytest.mark.integration

COLUMNS_SQL = """
SELECT table_schema || '.' || table_name AS name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = ANY($1::text[])
  AND table_name IN (SELECT table_name FROM information_schema.tables
                     WHERE table_schema = ANY($1::text[]) AND table_type = 'BASE TABLE')
"""

# Dữ liệu tối thiểu, không PII thật (09 bất biến 25).
BASE_ROWS = (
    "INSERT INTO ref.market (code, name, timezone, currency) "
    "VALUES ('SE', 'Sweden', 'Europe/Stockholm', 'SEK')",
    "INSERT INTO hr.position (code, name, grp) "
    "VALUES ('WAREHOUSE_MANAGER', 'Warehouse manager', 'warehouse')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
    "VALUES (1, 'warehouse', 'WH-A', 'Warehouse A', 59.3, 18.0, '14:00')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
    "VALUES (1, 'warehouse', 'WH-B', 'Warehouse B', 57.7, 11.9, '14:00')",
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES (1, 'E1', 'Test', 'One', 'WAREHOUSE_MANAGER', '2026-01-01')",
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES (1, 'E2', 'Test', 'Two', 'WAREHOUSE_MANAGER', '2026-01-01')",
)


ASSIGN = "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) VALUES "


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "0003")
    yield empty_db


@pytest.fixture
def seeded(db: str) -> str:
    execute(db, *BASE_ROWS)
    return db


def _columns(dsn: str) -> dict[str, dict[str, asyncpg.Record]]:
    out: dict[str, dict[str, asyncpg.Record]] = {}
    for row in fetch(dsn, COLUMNS_SQL, ["ref", "hr"]):
        out.setdefault(row["name"], {})[row["column_name"]] = row
    return out


def _rejects(
    dsn: str, error: type[asyncpg.IntegrityConstraintViolationError], constraint: str, *statements: str
) -> None:
    """Lệnh phải bị từ chối bởi ĐÚNG loại vi phạm và ĐÚNG ràng buộc (không chấp nhận lỗi cú pháp/kiểu)."""
    with pytest.raises(error) as caught:
        execute(dsn, *statements)
    assert caught.value.constraint_name == constraint


def test_migration_0002_0003_tables_and_columns_match_spec(db: str) -> None:
    spec = spec_tables_in("ref", "hr")
    actual = _columns(db)
    assert set(actual) == set(spec)  # 14 bảng ref + 12 bảng hr, không bảng thiết bị
    assert len(spec) == 26
    for table, columns in spec.items():
        assert set(actual[table]) == columns | COMMON_COLUMNS, table


def test_ASM_001_common_columns_on_every_table(db: str) -> None:
    for table, cols in _columns(db).items():
        for name in COMMON_COLUMNS:
            col = cols[name]
            assert col["data_type"] == "timestamp with time zone", (table, name)
            assert col["is_nullable"] == "NO", (table, name)
            assert col["column_default"] == "now()", (table, name)


def test_ASM_001_common_columns_filled_by_default(seeded: str) -> None:
    rows = fetch(seeded, "SELECT created_at, updated_at FROM hr.employee")
    assert rows and all(r["created_at"] is not None and r["updated_at"] is not None for r in rows)
    assert all(r["created_at"] == r["updated_at"] for r in rows)


def test_v_product_local_view_exists(db: str) -> None:
    assert fetch(db, "SELECT * FROM ref.v_product_local") == []


def test_location_checks_ck_wh_cutoff_and_ck_geo(seeded: str) -> None:
    _rejects(  # kho phải có giờ chốt lên hàng
        seeded,
        asyncpg.CheckViolationError,
        "ck_wh_cutoff",
        "INSERT INTO ref.location (market_id, type, code, name, lat, lon) "
        "VALUES (1, 'warehouse', 'WH-X', 'X', 59.0, 18.0)",
    )
    _rejects(  # kho/cửa hàng phải có tọa độ
        seeded,
        asyncpg.CheckViolationError,
        "ck_geo",
        "INSERT INTO ref.location (market_id, type, code, name) VALUES (1, 'store', 'ST-X', 'X')",
    )
    execute(  # dispatch_center không bắt buộc tọa độ / giờ chốt
        seeded,
        "INSERT INTO ref.location (market_id, type, code, name) VALUES (1, 'dispatch_center', 'DC-1', 'DC')",
    )


def test_app_user_kpi_scopes_v12(seeded: str) -> None:
    execute(
        seeded,
        "INSERT INTO ref.app_user (email, password_hash, roles) VALUES ('a@cfo.test', 'x', '{dispatcher}')",
        "INSERT INTO ref.app_user (email, password_hash, roles, kpi_scopes) "
        "VALUES ('b@cfo.test', 'x', '{viewer}', '{revenue_all}')",
    )
    assert [r["kpi_scopes"] for r in fetch(seeded, "SELECT kpi_scopes FROM ref.app_user ORDER BY id")] == [
        [],
        ["revenue_all"],
    ]
    _rejects(  # chỉ revenue_all / ops (không thêm scope mới)
        seeded,
        asyncpg.CheckViolationError,
        "app_user_kpi_scopes_check",
        "INSERT INTO ref.app_user (email, password_hash, roles, kpi_scopes) "
        "VALUES ('c@cfo.test', 'x', '{viewer}', '{finance}')",
    )
    with pytest.raises(asyncpg.InvalidTextRepresentationError) as caught:  # vai trò ngoài enum ref.user_role
        execute(
            seeded,
            "INSERT INTO ref.app_user (email, password_hash, roles) VALUES ('d@cfo.test', 'x', '{owner}')",
        )
    assert "ref.user_role" in str(caught.value)
    _rejects(  # khóa ngoài chéo fk_user_emp (0003)
        seeded,
        asyncpg.ForeignKeyViolationError,
        "fk_user_emp",
        "INSERT INTO ref.app_user (email, password_hash, roles, employee_id) "
        "VALUES ('e@cfo.test', 'x', '{warehouse}', 999)",
    )


def test_US_EMP_01_AC1_second_active_assignment_rejected(seeded: str) -> None:
    execute(
        seeded,
        ASSIGN + "(1, 1, '2026-01-01')",
    )
    _rejects(
        seeded, asyncpg.UniqueViolationError, "ux_one_active_assignment", ASSIGN + "(1, 2, '2026-02-01')"
    )
    # đóng phân công cũ rồi mở phân công mới thì hợp lệ (AC2 ở mức DB)
    execute(
        seeded,
        "UPDATE hr.employee_assignment SET end_date = '2026-01-31' WHERE employee_id = 1",
        ASSIGN + "(1, 2, '2026-02-01')",
    )


def test_US_EMP_01_AC3_second_primary_manager_rejected(seeded: str) -> None:
    execute(
        seeded,
        "INSERT INTO hr.location_manager (location_id, employee_id, level, valid_from) "
        "VALUES (1, 1, 'primary', '2026-01-01')",
        "INSERT INTO hr.location_manager (location_id, employee_id, level, valid_from) "
        "VALUES (1, 2, 'deputy', '2026-01-01')",
    )
    _rejects(
        seeded,
        asyncpg.UniqueViolationError,
        "ux_one_primary_manager",
        "INSERT INTO hr.location_manager (location_id, employee_id, level, valid_from) "
        "VALUES (1, 2, 'primary', '2026-01-01')",
    )


def test_vehicle_availability_overlap_rejected(seeded: str) -> None:
    execute(
        seeded,
        "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
        "required_licence) VALUES (1, 'V1', 'ABC123', 'Truck 1', 8000, 30, 'C')",
        "INSERT INTO ref.vehicle_availability (vehicle_id, during, kind) "
        "VALUES (1, '[2026-11-10 08:00+00, 2026-11-10 12:00+00)', 'maintenance')",
    )
    _rejects(
        seeded,
        asyncpg.ExclusionViolationError,
        "ex_vehicle_avail",
        "INSERT INTO ref.vehicle_availability (vehicle_id, during, kind) "
        "VALUES (1, '[2026-11-10 11:00+00, 2026-11-10 13:00+00)', 'unavailable')",
    )


def test_product_se_confirmed_requires_mapping(seeded: str) -> None:
    _rejects(
        seeded,
        asyncpg.CheckViolationError,
        "ck_se_confirmed",
        "INSERT INTO ref.product_se (local_sku, name, category, sale_unit, unit_price, mapping_status) "
        "VALUES ('SE-1', 'Item', 'Cement', 'bag', 10, 'confirmed')",
    )


def test_migration_0003_downgrade_to_0001_is_clean(db: str) -> None:
    command.downgrade(alembic_config(db), "0001")
    assert fetch(db, COLUMNS_SQL, ["ref", "hr"]) == []
    assert fetch(db, "SELECT 1 FROM information_schema.views WHERE table_schema = 'ref'") == []
    command.upgrade(alembic_config(db), "0003")
    assert len(_columns(db)) == 26
