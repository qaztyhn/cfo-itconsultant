"""0005_ops

Schema ops: stock_snapshot, inbound, transfer, customer_order (+external_handoff), order_line,
order_transition, date_negotiation, trip, trip_stop, milestone_event, proof_of_delivery theo trip_stop_id,
eta_forecast, alert (ux_alert_open_dedupe), notification (plan_id), contact_log, vehicle_position,
idempotency_key (05 mục 6).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
