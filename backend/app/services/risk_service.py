"""ETA và rủi ro (04 mục 6.3; US-RSK-01..03).

recalculate(order, trigger) chỉ khi có tín hiệu (event, gps, source_change, overdue_milestone,
morning_check, approval); ghi ops.eta_forecast phiên bản mới; orange → alert RISK_ORANGE; PREDICTED_LATE →
alert critical + notification DELAY draft (chỉ nếu lệch ≥ 30' so với khung đã báo); OVERDUE → alert
critical.

Owner: Dev 1 (A) — M7.
"""


async def recalculate(order_id: int, trigger: str) -> dict[str, object] | None:
    """TODO(#risk-recalculate)."""
    raise NotImplementedError
