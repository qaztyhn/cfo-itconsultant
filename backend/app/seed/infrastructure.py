"""Deterministic M1/M3 infrastructure subset from 08 section 5.1; add missing rows only."""

import argparse
import asyncio
from datetime import time
from decimal import Decimal

import holidays
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_engine, get_sessionmaker

WAREHOUSES = (
    ("GBG", "Göteborg DC", "57.70890", "11.97460"),
    ("STO", "Stockholm DC", "59.32930", "18.06860"),
    ("MLM", "Malmö DC", "55.60500", "13.00380"),
)


async def seed_infrastructure(session: AsyncSession, *, year: int) -> None:
    """Explicit demo year; do not depend on host date or reset operational rows."""
    await session.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    market = (await session.execute(text("SELECT id FROM ref.market WHERE code='SE'"))).scalar_one()
    for code, name, lat, lon in WAREHOUSES:
        await session.execute(
            text("""INSERT INTO ref.location
            (market_id,type,code,name,lat,lon,loading_cutoff_time)
            VALUES (:market,'warehouse',:code,:name,:lat,:lon,'15:00')
            ON CONFLICT (market_id,code) DO NOTHING"""),
            {
                "market": market,
                "code": code,
                "name": name,
                "lat": Decimal(lat),
                "lon": Decimal(lon),
            },
        )
        wh = (
            await session.execute(
                text("""SELECT id FROM ref.location
            WHERE market_id=:market AND code=:code AND type='warehouse'"""),
                {"market": market, "code": code},
            )
        ).scalar_one()
        for weekday in range(1, 6):
            for start, end, staff in (("06:00", "14:00", 7), ("14:00", "22:00", 5)):
                await session.execute(
                    text("""INSERT INTO hr.shift_template
                    (warehouse_id,weekday,start_time,end_time,useful_hours_per_staff,expected_staff)
                    SELECT :wh,:day,CAST(:start AS time),CAST(:end AS time),7.0,:staff
                    WHERE NOT EXISTS (SELECT 1 FROM hr.shift_template WHERE warehouse_id=:wh
                       AND weekday=:day AND start_time=CAST(:start AS time))"""),
                    {
                        "wh": wh,
                        "day": weekday,
                        "start": time.fromisoformat(start),
                        "end": time.fromisoformat(end),
                        "staff": staff,
                    },
                )
    for day, name in sorted(holidays.country_holidays("SE", years=[year]).items()):
        await session.execute(
            text("""INSERT INTO ref.market_holiday(market_id,holiday_date,name)
            VALUES (:market,:day,:name) ON CONFLICT (market_id,holiday_date) DO NOTHING"""),
            {"market": market, "day": day, "name": name},
        )


async def run(year: int) -> None:
    try:
        async with get_sessionmaker()() as session, session.begin():
            await seed_infrastructure(session, year=year)
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.year))
    except Exception:
        print("Infrastructure seed failed; check migrations and existing location identities.")
        return 1
    print("Infrastructure seed complete: warehouses, shifts and holidays only; full scenario seed pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
