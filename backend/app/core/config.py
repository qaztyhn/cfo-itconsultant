"""Cấu hình ứng dụng (Pydantic Settings) và MarketConfig.

Settings đọc biến môi trường (04 mục 13): DATABASE_URL, JWT_SECRET, ORS_API_KEY, SMTP_*,
SOURCE_SE_BASE_URL, SOURCE_SE_API_KEY, INTERNAL_TICK_KEY, APP_ENV, APP_NOW.

MarketConfig là model Pydantic của JSON `ref.market.config` (04 mục 8 + 06 Phụ lục A
`routing.allow_fallback`). Mọi số cấu hình đọc từ đây, KHÔNG hard-code (09 bất biến 20).

Owner: Dev 1 (luồng A) — M0.
"""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Biến môi trường. Bí mật không có trong mã/log."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""  # bắt buộc qua env; không ghi bí mật vào mã (09 bất biến 25)
    jwt_secret: str = ""
    jwt_ttl_hours: int = 8
    ors_api_key: str | None = None
    source_se_base_url: str = "http://localhost:8100/api/v1"
    source_se_api_key: str = ""
    internal_tick_key: str = ""
    app_env: str = "local"
    app_now: str | None = None  # ví dụ "2026-11-04T10:05:00+01:00" (08 mục 1.6)
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    """Settings singleton."""
    return Settings()


class LoadingCfg(BaseModel):
    base_min: int = 20
    min_per_ton: int = 6


class RankCfg(BaseModel):
    w_km: float = 0.5
    w_fill: float = 0.5
    dz_km_abs: float = 2
    dz_km_pct: float = 0.05
    dz_fill: float = 0.05
    tie_eps: float = 0.001


class RiskCfg(BaseModel):
    yellow_pct: int = 33
    orange_pct: int = 66
    consecutive_negative: int = 2
    min_reserve_min: int = 30
    milestone_grace_min: int = 30
    consecutive_min_gap_min: int = 5


class HoldCfg(BaseModel):
    ttl_min: int = 15
    max_extensions: int = 2


class GpsCfg(BaseModel):
    interval_min: int = 30
    lost_min: int = 60
    retention_days: int = 30


class NotifyCfg(BaseModel):
    quiet_hours: tuple[str, str] = ("21:00", "07:00")
    delay_min_shift_min: int = 30
    max_attempts: int = 3


class SyncCfg(BaseModel):
    interval_min: int = 5
    overlap_min: int = 2


class MultiVehicleCfg(BaseModel):
    max_arrival_spread_min: int = 30  # v1.2: các xe của một đơn tới chênh nhau tối đa


class RoutingCfg(BaseModel):
    allow_fallback: bool = True
    # Route đã lưu bằng fallback (đường chim bay) chỉ được dùng lại trong khoảng này; quá hạn thì thử ORS lại
    # để không dùng fallback vô thời hạn khi ORS đã khả dụng (review PR #65).
    fallback_retry_min: int = Field(default=60, gt=0)


class RetentionCfg(BaseModel):
    personal: int = 365
    order: int = 730


class MarketConfig(BaseModel):
    """MarketConfig mặc định [A] — 04 mục 8. Validate khi PUT /markets/{code}/config (US-ADM-02)."""

    working_days: list[int] = [1, 2, 3, 4, 5]
    default_receiving_hours: dict[str, tuple[str, str]] = {"mon-fri": ("07:00", "16:00")}
    search_days_max: int = 14
    reserve_safe_days: int = 2
    promise_window_hours: int = 2
    eta_round_min: int = 15
    delivery_share: float = Field(0.90, gt=0, le=1)
    final_inspection_hours: float = 0.5
    flag_multiplier_cap: float = 2.0
    loading: LoadingCfg = LoadingCfg()
    unloading: LoadingCfg = LoadingCfg()
    after_loaded_min: int = 10
    driver_max_hours_day: float = 9
    receiving_lead_days: int = 1
    multi_vehicle: MultiVehicleCfg = MultiVehicleCfg()
    transfer_lead_days_default: int = 1
    rank: RankCfg = RankCfg()
    risk: RiskCfg = RiskCfg()
    hold: HoldCfg = HoldCfg()
    stale_stock_min: int = 15
    gps: GpsCfg = GpsCfg()
    notify: NotifyCfg = NotifyCfg()
    data_retention_days: RetentionCfg = RetentionCfg()
    sync: SyncCfg = SyncCfg()
    routing: RoutingCfg = RoutingCfg()
