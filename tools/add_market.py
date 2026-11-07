"""Thêm một nước mới KHÔNG sửa lõi (US-INT-04; 07 mục 16): tạo dòng ref.market (shadow_mode = true),
bảng ref.product_<cc>, tái tạo view ref.v_product_local. Không file nào trong backend/app/engine thay đổi.

Dùng: python tools/add_market.py DK --name Denmark --timezone Europe/Copenhagen --currency DKK
Owner: Dev 2 (luồng B) — M1.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.adapters.market_setup import add_market  # noqa: E402
from app.core.db import get_engine, get_sessionmaker  # noqa: E402


async def run(args: argparse.Namespace) -> None:
    try:
        async with get_sessionmaker()() as session, session.begin():
            await add_market(
                session,
                args.code,
                name=args.name,
                timezone=args.timezone,
                currency=args.currency,
            )
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a shadow-mode market without modifying engine code")
    parser.add_argument("code")
    parser.add_argument("--name", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--currency", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception:
        print("Market setup failed; check configuration, migrations and existing market values.")
        return 1
    print("Market configured; review source credentials and configuration before enabling synchronization.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
