import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.integration.conftest import async_url


def transact[T](dsn: str, action: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), hide_parameters=True)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await action(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())
