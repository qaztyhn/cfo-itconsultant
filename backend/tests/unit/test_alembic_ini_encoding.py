"""alembic.ini phải đọc được trên mọi locale (PR qaztyhn/cfo-itconsultant#41: Windows cp1252).

Alembic nạp file bằng ConfigParser.read() với encoding mặc định của hệ điều hành, không phải UTF-8, nên mọi
ký tự ngoài ASCII (ví dụ comment tiếng Việt) có thể làm `alembic upgrade` hỏng trên Windows.
"""

import configparser
from pathlib import Path

import pytest

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_alembic_ini_is_ascii_only() -> None:
    raw = ALEMBIC_INI.read_bytes()
    bad = [(n, line) for n, line in enumerate(raw.splitlines(), start=1) if not line.isascii()]
    assert bad == [], f"alembic.ini must be ASCII-only; non-ASCII on lines {[n for n, _ in bad]}"


@pytest.mark.parametrize("encoding", ["cp1252", "latin-1", "ascii", "utf-8"])
def test_alembic_ini_parses_under_common_locale_encodings(encoding: str) -> None:
    parser = configparser.ConfigParser()
    parser.read_string(ALEMBIC_INI.read_bytes().decode(encoding))
    assert parser.get("alembic", "script_location") == "alembic"
    assert not parser.has_option("alembic", "sqlalchemy.url")  # DSN chỉ đến từ môi trường (09 bất biến 25)
