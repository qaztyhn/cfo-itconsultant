"""0012_pod_unique_per_trip_stop

DEC-OWNER-20261109 M6-1: a successful proof of delivery is unique per `trip_stop`, not per order.
One multi-vehicle order (several trips/stops) may have several delivered PODs.

- `ux_pod_one_delivered` (order_id WHERE result='delivered') is dropped.
- One POD per stop stays enforced by `proof_of_delivery_trip_stop_id_key` (0005); the documented partial
  unique index `ux_pod_one_delivered_trip_stop` is added alongside it.
- Forward migration: relaxing a uniqueness rule cannot fail on existing data. Downgrade fails closed if a
  multi-vehicle order already has several delivered PODs.
Owner: Dev 1.
"""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ops.ux_pod_one_delivered")
    op.execute(
        "CREATE UNIQUE INDEX ux_pod_one_delivered_trip_stop ON ops.proof_of_delivery (trip_stop_id) "
        "WHERE result = 'delivered'"
    )


def downgrade() -> None:
    # Re-adding the order-level rule fails if a multi-vehicle order already has several delivered PODs.
    op.execute("DROP INDEX IF EXISTS ops.ux_pod_one_delivered_trip_stop")
    op.execute(
        "CREATE UNIQUE INDEX ux_pod_one_delivered ON ops.proof_of_delivery (order_id) "
        "WHERE result = 'delivered'"
    )
