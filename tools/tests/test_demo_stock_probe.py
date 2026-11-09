"""Read-only stock diagnostic must never probe unsafe or remote environments."""
from tools.demo_stock_probe import observe


def test_stock_probe_refuses_unsafe_context_before_network_or_database():
    cases = [
        {},
        {"APP_ENV": "production", "DEMO_DISPOSABLE": "1",
         "APP_NOW": "2026-11-04T10:05:00+01:00",
         "COMPOSE_PROJECT_NAME": "cfo-demo-ci-abc"},
        {"APP_ENV": "test", "DEMO_DISPOSABLE": "1",
         "APP_NOW": "2026-11-04T10:05:00+01:00",
         "COMPOSE_PROJECT_NAME": "production"},
    ]
    for env in cases:
        assert observe(env) == {"source": "BLOCKED_UNSAFE_ENV", "cfo": "NOT_VERIFIED"}
