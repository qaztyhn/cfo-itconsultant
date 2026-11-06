"""Source instance configuration; credentials are supplied only through the environment."""

import os
import re
from dataclasses import dataclass, field

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    source_schema: str

    def __post_init__(self) -> None:
        try:
            url = make_url(self.database_url)
        except ArgumentError:
            raise ValueError("DATABASE_URL must be a PostgreSQL asyncpg URL") from None
        if url.drivername != "postgresql+asyncpg" or not url.database:
            raise ValueError("DATABASE_URL must select a PostgreSQL database using asyncpg")
        if not re.fullmatch(r"src_[a-z][a-z0-9_]*", self.source_schema):
            raise ValueError("SOURCE_SCHEMA must be a lowercase src_<market> identifier")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(os.environ.get("DATABASE_URL", ""), os.environ.get("SOURCE_SCHEMA", ""))
