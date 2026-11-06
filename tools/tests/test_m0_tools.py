"""Tool gates must reject missing contracts, no-op migrations and unhealthy HTTP 200s."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import check_m0_dependencies, harness

ROOT = Path(__file__).resolve().parents[2]


class DependencyTests(unittest.TestCase):
    def test_migration_stub_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            versions = root / "backend/alembic/versions"
            versions.mkdir(parents=True)
            (versions.parent / "env.py").write_text("# TODO\n", encoding="utf-8")
            (versions / "0001.py").write_text(
                "def upgrade():\n    raise NotImplementedError\n", encoding="utf-8"
            )
            with patch.object(check_m0_dependencies, "ROOT", root):
                self.assertEqual(len(check_m0_dependencies.blockers("migrations")), 2)

    def test_empty_openapi_is_not_a_passing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openapi.json"
            path.write_text(json.dumps({"paths": {}}), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/check_openapi.py"),
                    "--baseline",
                    str(path),
                    "--app",
                    "app.main:app",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("NOT VERIFIED", result.stdout)

    def test_smoke_rejects_error_payload_even_on_http_200(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"status":"error","db":"unavailable"}'
        with patch.object(harness, "urlopen", return_value=response), redirect_stdout(
            io.StringIO()
        ):
            self.assertFalse(harness.smoke())

    def test_contract_comparison_accepts_match_and_rejects_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = {"openapi": "3.1.0", "paths": {"/health": {"get": {}}}}
            path = root / "openapi.json"
            path.write_text(json.dumps(baseline), encoding="utf-8")
            module = root / "contract_fixture.py"
            module.write_text(
                f"class App:\n    def openapi(self):\n        return {baseline!r}\napp = App()\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(ROOT / "tools/check_openapi.py"),
                "--baseline",
                str(path),
                "--app",
                "contract_fixture:app",
            ]
            matched = subprocess.run(
                command, cwd=root, capture_output=True, check=False
            )
            self.assertEqual(matched.returncode, 0)
            path.write_text(
                json.dumps({"paths": {"/changed": {"get": {}}}}), encoding="utf-8"
            )
            changed = subprocess.run(
                command, cwd=root, capture_output=True, check=False
            )
            self.assertEqual(changed.returncode, 1)


if __name__ == "__main__":
    unittest.main()
