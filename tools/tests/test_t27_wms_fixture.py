"""Unit checks for the preparation gates and exact T26 WMS quantities."""

import io
import unittest
from contextlib import redirect_stderr
from decimal import Decimal
from unittest.mock import patch

from tools import t27_prepare_wms_fixture as helper


class T27WmsFixtureTests(unittest.TestCase):
    def test_US_APR_05_AC1_requires_exact_t26_plan_selector(self):
        stderr = io.StringIO()
        with (
            patch("sys.argv", ["helper", "--project", helper.T26_PROJECT, "--output", "unused"]),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as error,
        ):
            helper.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("T26 requires --source-ref, --plan-id and --rank", stderr.getvalue())

    def test_US_APR_05_AC1_converts_base_stock_without_rounding_away_units(self):
        self.assertEqual(helper.stock_units(Decimal("800"), Decimal("5")), Decimal("160.000"))
        with self.assertRaisesRegex(ValueError, "represented exactly"):
            helper.stock_units(Decimal("1"), Decimal("3"))
        with self.assertRaisesRegex(ValueError, "invalid conversion factor"):
            helper.stock_units(Decimal("1"), Decimal("0"))
