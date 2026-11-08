import hashlib
import json
from pathlib import Path

import pytest

from app.adapters.csv_bundle import CsvInputError, load_bundle, retry_action


def bundle(root: Path, data: bytes, **overrides: object) -> Path:
    (root / "data.csv").write_bytes(data)
    manifest = {
        "schema_version": "1",
        "market": "ZZ",
        "entity": "customers",
        "captured_at": "2026-11-04T10:00:00+01:00",
        "files": [{"role": "main", "path": "data.csv", "sha256": hashlib.sha256(data).hexdigest()}],
        **overrides,
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def read(path: Path, **options: int):
    return load_bundle(
        path, expected_market="ZZ", expected_entity="customers", headers={"main": ("id", "name")}, **options
    )


def test_D2_utf8_bom_quoted_comma_newline_and_non_pii_row_reject(tmp_path: Path) -> None:
    path = bundle(tmp_path, '\ufeffid,name\r\nC1,"Synthetic,\r\ncustomer"\r\nC2,private,extra\r\n'.encode())
    result = read(path)
    assert result.rows["main"][0].values == {"id": "C1", "name": "Synthetic,\r\ncustomer"}
    assert result.rejects[0].row_number == 3 and result.rejects[0].code == "INVALID_RECORD"
    assert "private" not in repr(result.rejects)


@pytest.mark.parametrize(
    "data,code",
    [
        (b"id,name\nC1,\xff", "INVALID_CSV_ENCODING_OR_SYNTAX"),
        (b'id,name\nC1,"unterminated', "INVALID_CSV_ENCODING_OR_SYNTAX"),
        (b"id,unknown\n", "INVALID_HEADER"),
        (b"id,id\n", "INVALID_HEADER"),
    ],
)
def test_D2_invalid_file_is_not_successfully_imported(tmp_path: Path, data: bytes, code: str) -> None:
    path = bundle(tmp_path, data)
    with pytest.raises(CsvInputError, match=code):
        read(path)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"schema_version": "2"}, "INVALID_MANIFEST"),
        ({"market": "OTHER"}, "SOURCE_SCOPE_MISMATCH"),
        ({"entity": "orders"}, "SOURCE_SCOPE_MISMATCH"),
        ({"captured_at": "2026-11-04T10:00:00"}, "INVALID_MANIFEST"),
        ({"unknown": "private"}, "INVALID_MANIFEST"),
    ],
)
def test_D2_explicit_schema_scope_and_aware_capture_are_required(
    tmp_path: Path, changes: dict[str, object], code: str
) -> None:
    path = bundle(tmp_path, b"id,name\n", **changes)
    with pytest.raises(CsvInputError, match=code):
        read(path)


def test_D2_hash_is_verified_on_original_bytes_before_decoding(tmp_path: Path) -> None:
    path = bundle(tmp_path, b"id,name\nC1,Synthetic\n")
    (tmp_path / "data.csv").write_bytes(b"id,name\nC1,changed\n")
    with pytest.raises(CsvInputError, match="FILE_HASH_MISMATCH"):
        read(path)


def test_D2_path_cannot_escape_bundle_or_use_duplicate_roles(tmp_path: Path) -> None:
    path = bundle(tmp_path, b"id,name\n")
    document = json.loads(path.read_text())
    document["files"][0]["path"] = "../outside.csv"
    (tmp_path.parent / "outside.csv").write_bytes(b"private")
    path.write_text(json.dumps(document))
    with pytest.raises(CsvInputError, match="UNSAFE_FILE_PATH") as error:
        read(path)
    assert "outside" not in str(error.value)
    document["files"][0]["path"] = "data.csv"
    document["files"].append(document["files"][0].copy())
    path.write_text(json.dumps(document))
    with pytest.raises(CsvInputError, match="INVALID_FILE_ROLES"):
        read(path)


def test_D2_configurable_limits_fail_closed(tmp_path: Path) -> None:
    path = bundle(tmp_path, b"id,name\nC1,Synthetic\nC2,Synthetic\n")
    with pytest.raises(CsvInputError, match="FILE_TOO_LARGE"):
        read(path, max_file_bytes=8)
    with pytest.raises(CsvInputError, match="ROW_LIMIT_EXCEEDED"):
        read(path, max_rows=1)


@pytest.mark.parametrize(
    "status,reviewed,result",
    [
        (None, False, "new_run"),
        ("ok", False, "skip"),
        ("failed", False, "new_run"),
        ("partial", False, "review_required"),
        ("partial", True, "new_run"),
        ("running", True, "conflict"),
    ],
)
def test_D2_retry_policy_preserves_history_instead_of_skipping_failures(status, reviewed, result) -> None:
    assert retry_action(status, it_reviewed=reviewed) == result
