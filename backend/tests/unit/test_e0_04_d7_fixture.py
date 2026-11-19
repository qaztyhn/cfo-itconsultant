"""E0-04 synthetic evidence remains date-bound, hash-bound and non-legal."""

import importlib.util
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.adapters.demo_d7_reader import DisposableD7Reader
from app.services.driver_history import verify_history


def test_e0_04_attested_driver_window_and_tamper_fail_closed(
    tmp_path, monkeypatch
) -> None:
    path = Path(__file__).resolve().parents[3] / "tools" / "e0_04_d7_fixture.py"
    spec = importlib.util.spec_from_file_location("e0_04_d7_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    module.main()

    reader = DisposableD7Reader(tmp_path)
    evidence = reader._load("DEMO-DRIVER-2", date(2026, 12, 1), 2)
    proof = verify_history(
        evidence,
        target_date=date(2026, 12, 1),
        zone=ZoneInfo("Europe/Stockholm"),
        now=datetime.fromisoformat("2026-12-01T10:05:00+01:00"),
        allow_synthetic=True,
    )
    assert proof.complete and not proof.legal_verified
    assert reader._load("DEMO-DRIVER-2", date(2026, 12, 2), 2) is None

    week = tmp_path / "history_week_08.json"
    week.write_bytes(week.read_bytes() + b" ")
    assert reader._load("DEMO-DRIVER-2", date(2026, 12, 1), 2) is None
