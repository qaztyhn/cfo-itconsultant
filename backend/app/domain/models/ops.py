"""Model SQLAlchemy cho schema `ops` (docs/05).

Bảng: stock_snapshot, inbound_shipment, stock_transfer, stock_transfer_line, customer_order, order_line,
order_transition, date_negotiation, delivery_trip, trip_stop, milestone_event, proof_of_delivery,
eta_forecast, alert, notification, customer_contact_log, vehicle_position, idempotency_key.
Không đổi tên bảng/cột (09 mục 6). TODO(#M1-models).
Owner: Dev 1 (luồng A) — M1.
"""
