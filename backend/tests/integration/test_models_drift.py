"""Model SQLAlchemy khớp schema do migration tạo (không drift) — 09 mục 6: migration là nguồn sự thật.

So sánh trên PostgreSQL đã `upgrade head`:
1. Bảng/cột của model == DDL trong docs/05 (+ cột chung ASM-001).
2. `alembic.autogenerate.compare_metadata`: không thiếu/thừa bảng, cột; kiểu, nullable, khóa ngoài khớp.
   Chỉ mục và UNIQUE/CHECK/EXCLUDE không khai báo ở model (DB thực thi; đã có test migration riêng).
3. Nhãn enum của model == enum trong DB.
MODEL_SCHEMAS = cả 6 schema (57 bảng) từ M1-C; khóa ngoài ops → plan đã được khai báo.
View chỉ đọc (VIEW_METADATA) so cột với information_schema của view.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models import Base
from app.domain.models.views import VIEW_METADATA
from tests.integration.conftest import (
    _admin_exec,
    _with_database,
    alembic_config,
    async_url,
    execute,
    fetch,
)
from tests.integration.spec05 import COMMON_COLUMNS, spec_tables_in

pytestmark = pytest.mark.integration

MODEL_SCHEMAS: tuple[str, ...] = ("ref", "hr", "stg", "ops", "plan", "audit")


@pytest.fixture(scope="module")
def head_db(server_dsn: str) -> Iterator[str]:
    """Một DB trống, migrate tới head, dùng chung cho các test chỉ đọc trong module này."""
    name = f"cfo_drift_{uuid.uuid4().hex[:10]}"
    asyncio.run(_admin_exec(server_dsn, f'CREATE DATABASE "{name}"'))
    dsn = _with_database(server_dsn, name)
    try:
        command.upgrade(alembic_config(dsn), "head")
        yield dsn
    finally:
        asyncio.run(_admin_exec(server_dsn, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _model_tables() -> dict[str, Any]:
    return {t.fullname: t for t in Base.metadata.sorted_tables if t.schema in MODEL_SCHEMAS}


def _include_name(name: str | None, type_: str, parent_names: dict[str, Any]) -> bool:
    if type_ == "schema":
        return name in MODEL_SCHEMAS
    if type_ == "table":
        return parent_names.get("schema_name") in MODEL_SCHEMAS
    return True


def _include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    if type_ == "foreign_key_constraint":
        # Khóa ngoài tới schema chưa có model (vd. ops → plan trước M1-C) được khai báo ở PR sau.
        return getattr(obj.referred_table, "schema", None) in MODEL_SCHEMAS
    return type_ not in ("index", "unique_constraint")


def _compare(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection,
        opts={
            "include_schemas": True,
            "include_name": _include_name,
            "include_object": _include_object,
            "compare_type": True,
        },
    )
    return list(compare_metadata(context, Base.metadata))


def _diff(dsn: str) -> list[Any]:
    async def run() -> list[Any]:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(_compare)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_models_cover_exactly_the_spec_tables_and_columns() -> None:
    spec = spec_tables_in(*MODEL_SCHEMAS)
    models = _model_tables()
    assert set(models) == set(spec)
    for name, table in models.items():
        assert {c.name for c in table.columns} == spec[name] | COMMON_COLUMNS, name


def test_models_have_no_drift_against_migrated_database(head_db: str) -> None:
    assert _diff(head_db) == []


def test_model_enum_labels_match_database(head_db: str) -> None:
    db_enums = {
        r["name"]: list(r["labels"])
        for r in fetch(
            head_db,
            "SELECT n.nspname || '.' || t.typname AS name, "
            "array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels "
            "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace GROUP BY 1",
        )
    }
    checked = 0
    for table in _model_tables().values():
        for column in table.columns:
            col_type = getattr(column.type, "item_type", column.type)  # enum hoặc mảng enum
            if isinstance(col_type, SAEnum):
                assert list(col_type.enums) == db_enums[f"{col_type.schema}.{col_type.name}"], column
                checked += 1
    assert checked > 0


def test_models_never_create_schema_objects() -> None:
    """Model không tự tạo kiểu enum (migration mới tạo — 09 mục 6)."""
    for table in _model_tables().values():
        for column in table.columns:
            col_type = getattr(column.type, "item_type", column.type)
            if isinstance(col_type, SAEnum):
                assert col_type.create_type is False, column


def test_drift_check_detects_a_missing_column(empty_db: str) -> None:
    """Đối chứng: xóa một cột model có khai báo trong DB tạm → compare_metadata phải báo khác biệt."""
    command.upgrade(alembic_config(empty_db), "head")
    table = _model_tables()[f"{MODEL_SCHEMAS[0]}.location"]
    execute(empty_db, f"ALTER TABLE {table.fullname} DROP COLUMN efficiency_factor")
    diff = _diff(empty_db)
    assert any(d[0] == "add_column" and d[3].name == "efficiency_factor" for d in diff), diff


def test_all_57_tables_are_modelled() -> None:
    assert len(_model_tables()) == 57


def test_read_only_views_match_database(head_db: str) -> None:
    rows_ = fetch(
        head_db,
        "SELECT table_schema || '.' || table_name AS name, "
        "array_agg(column_name::text ORDER BY ordinal_position) AS columns "
        "FROM information_schema.columns WHERE table_schema IN ('ref', 'audit') "
        "AND table_name LIKE 'v\\_%' GROUP BY 1",
    )
    db_views = {r["name"]: list(r["columns"]) for r in rows_}
    model_views = {t.fullname: [c.name for c in t.columns] for t in VIEW_METADATA.sorted_tables}
    assert model_views == db_views
    assert not set(model_views) & set(Base.metadata.tables)  # view không nằm trong metadata của bảng
