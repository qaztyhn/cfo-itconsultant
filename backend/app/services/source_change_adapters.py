"""Trusted T14 adapters for the T07 source-change callbacks (contract: `app.services.ingest_types`).

`ReplanSource = (session, order, source_order) -> run_id | None` is satisfied by `replan_source()`. It joins
the CALLER's transaction (no commit of its own) and reuses the fresh-engine `planning_service.suggest_replan`,
keeping every guarantee of that service: an unheld advisory run only, never an approval, the committed plan
and its stock/labour/vehicle reservations untouched, one run per source version, and only an alert (no
replacement plan) once the order is DISPATCHED.

The matching `SourceRisk` adapter is NOT here: `risk_service.recalculate` is still a stub on `main` (M7,
#131, is open) and the trusted source-signal watermark it needs has no reviewed contract. Until then T07 must
keep its "risk handoff unavailable" behaviour; nothing here fakes a risk result.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.order_wire import SourceOrder
from app.domain.models.ops import CustomerOrder
from app.services import planning_service
from app.services.ingest_types import ReplanSource
from app.services.planning_inputs import load_inputs

SOURCE_CHANGE = "source_change"


def replan_source(*, inputs_loader: planning_service.InputLoader = load_inputs) -> ReplanSource:
    async def adapter(session: AsyncSession, order: CustomerOrder, source: SourceOrder) -> int | None:
        return await planning_service.suggest_replan(
            order.id, SOURCE_CHANGE, session=session, inputs_loader=inputs_loader
        )

    return adapter
