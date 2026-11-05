"""Bước 5 — giải thích bằng mẫu câu cố định, không AI (04 mục 6.2; 09 mục 8).

reason_codes của hạng 1: LOWEST_SCORE_OF_3 | LOWEST_SCORE_OF_2 | ONLY_FEASIBLE (+ STOCK_*, TRUCK_OK,
RESERVE_SAFE/RESERVE_TIGHT). Cấm chữ "cheapest/cost/SEK". Mỗi ứng viên bị loại có detail.message.

Owner: Dev 1 (luồng A).
"""

from app.engine.types import PlanCandidate, RejectedCandidate


def reason_codes_for(c: PlanCandidate, total_feasible: int) -> tuple[str, ...]:
    """Sinh mã lý do. TODO(#M4-explain)."""
    raise NotImplementedError


def explanation_for(c: PlanCandidate, total_feasible: int, warehouse_name: str) -> str:
    """Câu giải thích tiếng Anh từ mẫu cố định. TODO(#M4-explain)."""
    raise NotImplementedError


def rejection_message(r: RejectedCandidate) -> str:
    """Câu giải thích có số cho ứng viên bị loại (03 mục 5.2). TODO(#M4-explain)."""
    raise NotImplementedError
