"""Router /api/v1 gộp mọi module (06)."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    alerts,
    auth,
    execution,
    gps,
    health,
    hr,
    internal,
    kpi,
    mapping,
    notifications,
    orders,
    planning,
    revenue,
    transfers,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(orders.router)
router.include_router(planning.router)
router.include_router(transfers.router)
router.include_router(execution.router)
router.include_router(gps.router)
router.include_router(alerts.router)
router.include_router(notifications.router)
router.include_router(mapping.router)
router.include_router(hr.router)
router.include_router(kpi.router)
router.include_router(revenue.router)
router.include_router(admin.router)
router.include_router(health.router)
router.include_router(internal.router)
