"""E0-04 synthetic evidence remains date-bound, hash-bound and non-legal."""

import importlib.util
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.adapters import demo_d7_reader
from app.adapters.demo_d7_reader import DisposableD7Reader
from app.services.driver_history import verify_history


def test_e0_04_attested_driver_window_and_tamper_fail_closed(tmp_path, monkeypatch) -> None:
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


def test_T12_execution_day_has_independent_attested_synthetic_56_day_proof(tmp_path, monkeypatch) -> None:
    path = Path(__file__).resolve().parents[3] / "tools" / "e0_04_d7_fixture.py"
    spec = importlib.util.spec_from_file_location("e0_04_d7_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "TARGET", date(2026, 12, 2))
    module.main()

    reader = DisposableD7Reader(tmp_path)
    evidence = reader._load("DEMO-DRIVER-2", date(2026, 12, 2), 2)
    proof = verify_history(
        evidence,
        target_date=date(2026, 12, 2),
        zone=ZoneInfo("Europe/Stockholm"),
        now=datetime.fromisoformat("2026-12-02T06:42:00+01:00"),
        allow_synthetic=True,
    )
    assert proof.complete
    assert proof.source_kind == "synthetic_demo"
    assert not proof.legal_verified
    assert reader._load("DEMO-DRIVER-2", date(2026, 12, 1), 2) is None

    week = tmp_path / "history_week_07.json"
    week.write_bytes(week.read_bytes() + b" ")
    assert reader._load("DEMO-DRIVER-2", date(2026, 12, 2), 2) is None


def test_T12_execution_reader_is_frozen_to_disposable_shift_and_exact_mount(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setenv("DEMO_D7_FIXTURE_DIR", "/srv/e0_04_d7/step8_dec02")

    def enabled(at: str, environment: str = "test") -> bool:
        monkeypatch.setattr(
            demo_d7_reader,
            "get_settings",
            lambda: SimpleNamespace(app_env=environment, app_now=at),
        )
        return demo_d7_reader._demo_enabled()

    assert enabled("2026-12-02T06:42:03+01:00")
    assert not enabled("2026-12-02T05:59:00+01:00")
    assert not enabled("2026-12-02T14:00:00+01:00")
    assert not enabled("2026-12-03T08:00:00+01:00")
    assert not enabled("2026-12-02T06:42:03")
    assert not enabled("2026-12-02T06:42:03+01:00", "production")
    monkeypatch.setenv("DEMO_D7_FIXTURE_DIR", "/srv/other")
    assert not enabled("2026-12-02T06:42:03+01:00")
    monkeypatch.delenv("DEMO_DISPOSABLE")
    assert not enabled("2026-12-02T06:42:03+01:00")
