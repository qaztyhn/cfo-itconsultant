"""Separate Source and synthetic WMS batch identities; link accepted stock writes."""

from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ops.stock_write_run ADD COLUMN source_kind text NOT NULL DEFAULT 'source' "
        "CONSTRAINT ck_stock_write_source_kind CHECK (source_kind IN ('source','wms_synthetic'))"
    )
    op.execute("ALTER TABLE ops.stock_write_run ADD COLUMN ingest_run_id bigint REFERENCES stg.sync_run(id)")
    op.execute(
        "ALTER TABLE ops.stock_write_run DROP CONSTRAINT stock_write_run_market_id_source_batch_id_key"
    )
    op.execute(
        "ALTER TABLE ops.stock_write_run ADD CONSTRAINT uq_stock_write_origin_batch "
        "UNIQUE (market_id, source_kind, source_batch_id)"
    )
    op.execute(
        "ALTER TABLE ops.wms_reservation_intent ADD COLUMN stock_write_run_id bigint "
        "REFERENCES ops.stock_write_run(id), ADD COLUMN verified_batch_payload jsonb, "
        "ADD COLUMN verified_batch_sha256 text "
        "CONSTRAINT ck_wms_verified_batch_sha CHECK "
        "(verified_batch_sha256 IS NULL OR length(verified_batch_sha256)=64)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ops.wms_reservation_intent DROP COLUMN verified_batch_sha256, "
        "DROP COLUMN verified_batch_payload, DROP COLUMN stock_write_run_id"
    )
    op.execute("ALTER TABLE ops.stock_write_run DROP CONSTRAINT uq_stock_write_origin_batch")
    op.execute(
        "ALTER TABLE ops.stock_write_run ADD CONSTRAINT stock_write_run_market_id_source_batch_id_key "
        "UNIQUE (market_id, source_batch_id)"
    )
    op.execute("ALTER TABLE ops.stock_write_run DROP COLUMN source_kind")
    op.execute("ALTER TABLE ops.stock_write_run DROP COLUMN ingest_run_id")
