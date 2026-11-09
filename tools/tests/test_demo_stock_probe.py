"""Stock observation cannot execute on non-disposable contexts."""
import unittest

from tools.demo_stock_probe import observe


class StockProbeGuards(unittest.TestCase):
    def test_unsafe_context_denied_before_any_http_or_database_read(self):
        contexts = [
            {},
            {
                "APP_ENV": "production", "DEMO_DISPOSABLE": "1",
                "APP_NOW": "2026-11-04T10:05:00+01:00",
                "COMPOSE_PROJECT_NAME": "cfo-demo-ci-abc",
            },
            {
                "APP_ENV": "test", "DEMO_DISPOSABLE": "1",
                "APP_NOW": "2026-11-04T10:05:00+01:00",
                "COMPOSE_PROJECT_NAME": "production",
            },
        ]
        for env in contexts:
            with self.subTest(env=env):
                self.assertEqual(
                    observe(env), {"source": "BLOCKED_UNSAFE_ENV", "cfo": "NOT_VERIFIED"}
                )
