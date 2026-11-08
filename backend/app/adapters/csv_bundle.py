"""D2 offline CSV boundary. No DB writes, upload endpoint, approval or checkpoint handling."""

import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class CsvInputError(ValueError):
    """Static machine code only; never echo paths, CSV cells or customer information."""


class FileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"]
    market: str = Field(min_length=1)
    entity: str = Field(min_length=1)
    captured_at: AwareDatetime
    files: list[FileSpec] = Field(min_length=1)

    @field_validator("captured_at", mode="before")
    @classmethod
    def iso_capture(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
        ):
            raise ValueError("ISO timestamp with offset required")
        return value


@dataclass(frozen=True)
class CsvReject:
    role: str
    row_number: int
    code: str


@dataclass(frozen=True)
class CsvRow:
    row_number: int
    values: dict[str, str]


@dataclass(frozen=True)
class CsvBundle:
    manifest: Manifest
    rows: dict[str, tuple[CsvRow, ...]]
    rejects: tuple[CsvReject, ...]


def _bytes(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise CsvInputError("FILE_TOO_LARGE")
        return data
    except OSError:
        raise CsvInputError("FILE_UNAVAILABLE") from None


def load_bundle(
    manifest_path: Path,
    *,
    expected_market: str,
    expected_entity: str,
    headers: Mapping[str, tuple[str, ...]],
    max_file_bytes: int = 10 * 1024 * 1024,
    max_rows: int = 100000,
) -> CsvBundle:
    """Read each file once, verify its exact bytes, then parse RFC4180 comma records.

    Header definitions come from a reviewed versioned entity decoder, never from the upload.
    Technical limits can be configured by the caller. Record numbers count CSV records, so a
    quoted multiline cell does not change the identity used in reject metadata.
    """
    if max_file_bytes < 1 or max_rows < 1:
        raise ValueError("CSV technical limits must be positive")
    try:
        manifest = Manifest.model_validate(json.loads(_bytes(manifest_path, 65536).decode("utf-8-sig")))
    except (ValueError, UnicodeError):
        raise CsvInputError("INVALID_MANIFEST") from None
    if manifest.market != expected_market or manifest.entity != expected_entity:
        raise CsvInputError("SOURCE_SCOPE_MISMATCH")
    roles = [item.role for item in manifest.files]
    if len(roles) != len(set(roles)) or set(roles) != set(headers):
        raise CsvInputError("INVALID_FILE_ROLES")
    root = manifest_path.resolve().parent
    rows: dict[str, tuple[CsvRow, ...]] = {}
    rejects: list[CsvReject] = []
    paths: set[Path] = set()
    for item in manifest.files:
        relative = Path(item.path)
        try:
            target = (root / relative).resolve(strict=True)
        except (OSError, RuntimeError):
            raise CsvInputError("FILE_UNAVAILABLE") from None
        if (
            relative.is_absolute()
            or ":" in item.path
            or not target.is_relative_to(root)
            or target in paths
            or not target.is_file()
        ):
            raise CsvInputError("UNSAFE_FILE_PATH")
        paths.add(target)
        data = _bytes(target, max_file_bytes)
        if hashlib.sha256(data).hexdigest() != item.sha256:
            raise CsvInputError("FILE_HASH_MISMATCH")
        try:
            reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), delimiter=",", strict=True)
            expected = headers[item.role]
            if tuple(next(reader, ())) != expected:
                raise CsvInputError("INVALID_HEADER")
            records: list[CsvRow] = []
            for number, cells in enumerate(reader, start=2):
                if number - 1 > max_rows:
                    raise CsvInputError("ROW_LIMIT_EXCEEDED")
                if len(cells) != len(expected) or any("\x00" in cell for cell in cells):
                    rejects.append(CsvReject(item.role, number, "INVALID_RECORD"))
                    continue
                records.append(CsvRow(number, dict(zip(expected, cells, strict=True))))
            rows[item.role] = tuple(records)
        except (UnicodeError, csv.Error):
            raise CsvInputError("INVALID_CSV_ENCODING_OR_SYNTAX") from None
    return CsvBundle(manifest, rows, tuple(rejects))


def retry_action(
    previous_status: Literal["ok", "failed", "partial", "running"] | None, *, it_reviewed: bool = False
) -> Literal["new_run", "skip", "review_required", "conflict"]:
    """D2 policy only. Caller must look up scoped hashes and lock/create run history atomically."""
    if previous_status not in {None, "ok", "failed", "partial", "running"}:
        raise ValueError("Unknown CSV run status")
    if previous_status == "ok":
        return "skip"
    if previous_status == "running":
        return "conflict"
    if previous_status == "partial" and not it_reviewed:
        return "review_required"
    return "new_run"
