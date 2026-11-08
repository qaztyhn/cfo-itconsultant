import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.retention_review import main


class RetentionReviewTests(unittest.TestCase):
    def run_cli(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with (
                patch("sys.argv", ["retention_review", "--metadata", str(path)]),
                patch.dict("os.environ", {"APP_NOW": "2026-11-08T12:00:00Z"}),
                contextlib.redirect_stdout(output),
            ):
                status = main()
        return status, output.getvalue()

    def test_D5_metadata_review_only_outputs_counts_with_deletion_disabled(self):
        status, output = self.run_cli(
            {
                "policy_version": "2026-11-08.1",
                "synthetic_only": True,
                "items": [{"category": "unknown-private-value", "timezone": "UTC"}],
            }
        )
        self.assertEqual(status, 0)
        result = json.loads(output)
        self.assertFalse(result["deletion_enabled"])
        self.assertEqual(result["counts"], {"unknown": {"blocked_unknown_category": 1}})
        self.assertNotIn("private-value", output)

    def test_D5_schema_errors_do_not_echo_private_values(self):
        status, output = self.run_cli(
            {
                "policy_version": "2026-11-08.1",
                "synthetic_only": True,
                "customer_email": "private-sensitive-value@example.test",
                "items": [],
            }
        )
        self.assertEqual(status, 1)
        self.assertNotIn("private-sensitive-value", output)

    def test_D5_real_data_mode_is_rejected(self):
        status, _ = self.run_cli(
            {"policy_version": "2026-11-08.1", "synthetic_only": False, "items": []}
        )
        self.assertEqual(status, 1)
