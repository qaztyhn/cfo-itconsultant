"""Disposable D7 fixture-reader regression tests. No production eligibility claims."""

import asyncio
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.adapters import demo_d7_reader
from app.services.driver_history import verify_history

TARGET = date(2026, 11, 4)
NOW = datetime.fromisoformat("2026-11-04T10:05:00+01:00")


def put(root: Path, name: str, data: dict) -> None:
    (root / name).write_text(json.dumps(data), encoding="utf-8")


def fixture(root: Path) -> None:
    days = [TARGET - timedelta(days=n) for n in range(56, 0, -1)]
    put(
        root,
        "manifest.json",
        {
            "source": "synthetic_demo",
            "market": "SE",
            "timezone": "Europe/Stockholm",
            "history_start": days[0].isoformat(),
            "history_end": days[-1].isoformat(),
            "history_days_per_driver": 56,
            "offline_only": True,
        },
    )
    put(
        root,
        "drivers.json",
        {"records": [{"driver_code": "D01", "employee_no": "DEMO-DRIVER-1", "market": "SE"}]},
    )
    for n in range(8):
        records = []
        for day in days[n * 7 : (n + 1) * 7]:
            stamp = day.isoformat()
            if day.weekday() >= 5:
                records.append(
                    {
                        "driver_code": "D01",
                        "work_date": stamp,
                        "coverage_status": "complete",
                        "verified_off_duty": True,
                        "verified_rest_window": {
                            "start": stamp + "T00:00:00+01:00",
                            "end": stamp + "T23:59:00+01:00",
                        },
                    }
                )
            else:
                records.append(
                    {
                        "driver_code": "D01",
                        "work_date": stamp,
                        "coverage_status": "complete",
                        "verified_off_duty": False,
                        "duty_start": stamp + "T08:00:00+01:00",
                        "duty_end": stamp + "T16:00:00+01:00",
                        "driving_intervals": [
                            {"start": stamp + "T09:00:00+01:00", "end": stamp + "T11:00:00+01:00"}
                        ],
                    }
                )
        put(
            root, f"history_week_{n + 1:02d}.json", {"source": "synthetic_demo", "records": records}
        )
    attest(root)


def attest(root: Path, **overrides) -> None:
    hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in demo_d7_reader.FILES
    }
    data = {
        "source_kind": "synthetic_demo",
        "verified_by": "Synthetic Test Reviewer",
        "verified_at": "2026-11-03T10:00:00+01:00",
        "expires_at": "2026-11-11T10:00:00+01:00",
        "revoked": False,
        "sha256": hashes,
    }
    data.update(overrides)
    put(root, "verification.json", data)


class Session:
    async def get(self, model, pk):
        return SimpleNamespace(employee_no="DEMO-DRIVER-1") if pk == 2 else None


def read(root, monkeypatch, *, app_env="test"):
    monkeypatch.setattr(
        demo_d7_reader, "get_settings",
        lambda: SimpleNamespace(app_env=app_env, app_now=demo_d7_reader.DEMO_NOW),
    )
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    return asyncio.run(demo_d7_reader.DisposableD7Reader(root).read(Session(), 2, "SE", TARGET))


def test_attested_synthetic_full_56_days_passes_only_demo_verifier(tmp_path, monkeypatch):
    fixture(tmp_path)
    evidence = read(tmp_path, monkeypatch)
    assert evidence is not None
    proof = verify_history(
        evidence,
        target_date=TARGET,
        zone=ZoneInfo("Europe/Stockholm"),
        now=NOW,
        allow_synthetic=True,
    )
    assert proof.complete is True and proof.legal_verified is False
    assert not verify_history(
        evidence,
        target_date=TARGET,
        zone=ZoneInfo("Europe/Stockholm"),
        now=NOW,
        allow_synthetic=False,
    ).complete


def test_missing_attestation_or_mismatched_file_fails_closed(tmp_path, monkeypatch):
    fixture(tmp_path)
    (tmp_path / "verification.json").unlink()
    assert read(tmp_path, monkeypatch) is None
    attest(tmp_path)
    (tmp_path / "history_week_01.json").write_text("{}", encoding="utf-8")
    assert read(tmp_path, monkeypatch) is None


def test_missing_day_cannot_be_covered_by_a_valid_hash(tmp_path, monkeypatch):
    fixture(tmp_path)
    path = tmp_path / "history_week_01.json"
    week = json.loads(path.read_text(encoding="utf-8"))
    week["records"].pop()
    put(tmp_path, path.name, week)
    attest(tmp_path)
    evidence = read(tmp_path, monkeypatch)
    assert evidence is not None
    proof = verify_history(
        evidence,
        target_date=TARGET,
        zone=ZoneInfo("Europe/Stockholm"),
        now=NOW,
        allow_synthetic=True,
    )
    assert not proof.complete and "DAY_MISSING" in proof.reasons


def test_wrong_window_and_production_fail_closed(tmp_path, monkeypatch):
    fixture(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["history_start"] = "2026-09-14"
    put(tmp_path, "manifest.json", manifest)
    attest(tmp_path)
    assert read(tmp_path, monkeypatch) is None
    fixture(tmp_path)
    assert read(tmp_path, monkeypatch, app_env="production") is None


def test_expired_attestation_does_not_prove_eligibility(tmp_path, monkeypatch):
    fixture(tmp_path)
    attest(tmp_path, expires_at="2026-11-04T09:00:00+01:00")
    evidence = read(tmp_path, monkeypatch)
    assert evidence is not None
    proof = verify_history(
        evidence,
        target_date=TARGET,
        zone=ZoneInfo("Europe/Stockholm"),
        now=NOW,
        allow_synthetic=True,
    )
    assert not proof.complete and "EVIDENCE_EXPIRED" in proof.reasons
