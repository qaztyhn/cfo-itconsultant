"""D4 versioned status/ETA-only templates shared by preview and outbox delivery.

No arbitrary variable interpolation, customer/staff names, source notes or coordinates.
Locale en is the documented pilot language; unknown locales fail closed until translated/reviewed.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, model_validator

Template = Literal["CONFIRMED", "DISPATCHED", "DELIVERED", "FAILED", "DELAY"]
TEMPLATE_VERSION = "1"
PublicReference = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9._/-]{0,79}$")]
PHRASES = {
    "CONFIRMED": "Delivery confirmed.",
    "DISPATCHED": "Delivery dispatched.",
    "DELIVERED": "Delivery completed.",
    "FAILED": "Delivery was unsuccessful.",
    "DELAY": "Delivery timing has changed.",
}


class EtaWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> "EtaWindow":
        if self.start >= self.end:
            raise ValueError("ETA window must be ordered")
        return self


class MessageVariables(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_order_ref: PublicReference
    eta_window: EtaWindow | None = None


@dataclass(frozen=True)
class RenderedMessage:
    template: Template
    version: str
    locale: str
    subject: str
    body: str


def render_message(
    template: Template, variables: MessageVariables, *, locale: str, timezone: str
) -> RenderedMessage:
    if template not in PHRASES or locale.lower().replace("_", "-").split("-")[0] != "en":
        raise ValueError("Unsupported notification template or locale")
    zone = ZoneInfo(timezone)
    if template == "DELAY" and variables.eta_window is None:
        raise ValueError("DELAY requires a validated ETA window")
    body = f"Order {variables.public_order_ref}: {PHRASES[template]}"
    if variables.eta_window is not None:
        start = variables.eta_window.start.astimezone(zone)
        end = variables.eta_window.end.astimezone(zone)
        body += (
            f" Delivery window: {start.isoformat(timespec='minutes')} – {end.isoformat(timespec='minutes')}."
        )
    return RenderedMessage(template, TEMPLATE_VERSION, locale, f"Order {variables.public_order_ref}", body)


def approved_window(start: datetime | None, end: datetime | None) -> EtaWindow | None:
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise ValueError("Approved delivery window is incomplete")
    return EtaWindow(start=start, end=end)
