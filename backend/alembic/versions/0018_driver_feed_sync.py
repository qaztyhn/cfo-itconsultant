"""Journal the two DEC-R3-07 feeds independently."""

from alembic import op

revision = "0018"
down_revision = "0017"

PREVIOUS = "'orders','customers','products','stock','inbound','fleet'"
DRIVER_FEEDS = "'driver-availability','driver-eligibility'"


def upgrade() -> None:
    op.execute("ALTER TABLE stg.sync_run DROP CONSTRAINT sync_run_entity_check")
    op.execute(
        f"ALTER TABLE stg.sync_run ADD CONSTRAINT sync_run_entity_check "
        f"CHECK (entity IN ({PREVIOUS},{DRIVER_FEEDS}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stg.sync_run DROP CONSTRAINT sync_run_entity_check")
    # Retain historical run/reject logs when reverting to the former entity set.
    op.execute(f"UPDATE stg.sync_run SET entity = 'fleet' WHERE entity IN ({DRIVER_FEEDS})")
    op.execute(
        f"ALTER TABLE stg.sync_run ADD CONSTRAINT sync_run_entity_check CHECK (entity IN ({PREVIOUS}))"
    )
