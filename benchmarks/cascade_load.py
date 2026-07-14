"""Cascade router latency benchmark (locust loadtest senaryosu).

Run with locust:
  locust -f benchmarks/cascade_load.py --host http://localhost:8000 \\
         --users 100 --spawn-rate 10 --run-time 5m \\
         --html benchmarks/results/01_cascade_load.html \\
         --csv benchmarks/results/01_cascade_load --headless

With no live backend (in CI, or under a freeze) `python benchmarks/cascade_load.py`
does a dry run: the locust import is skipped and it only prints the scenario.
"""

from __future__ import annotations

import sys


def _scenario_summary() -> dict:
    return {
        "name": "cascade_load",
        "users": 100,
        "spawn_rate": 10,
        "wait_time_range": [0.1, 0.5],
        "endpoint": "/v1/cascade/ask",
        "method": "POST",
        "payload_template": {"prompt": "test", "model": "gptoss"},
        "duration_minutes": 5,
        "expected_p99_ms": 1000,
    }


try:
    from locust import HttpUser, between, task

    class CascadeUser(HttpUser):
        wait_time = between(0.1, 0.5)

        @task(3)
        def ask_gptoss(self):
            self.client.post(
                "/v1/cascade/ask",
                json={"prompt": "test prompt", "model": "gptoss"},
                timeout=30,
                name="cascade_ask_gptoss",
            )

        @task(1)
        def ask_kimi(self):
            self.client.post(
                "/v1/cascade/ask",
                json={"prompt": "test prompt", "model": "kimi"},
                timeout=30,
                name="cascade_ask_kimi",
            )
except ImportError:
    if __name__ == "__main__":
        import json

        print("locust not available — printing scenario summary instead:")
        print(json.dumps(_scenario_summary(), indent=2))
        sys.exit(0)


if __name__ == "__main__":
    import json

    print(json.dumps(_scenario_summary(), indent=2))
