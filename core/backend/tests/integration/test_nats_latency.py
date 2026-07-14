"""NATS JetStream live broker integration test.

Skipped unless ABS_NATS_URL points at a reachable JetStream-enabled
NATS server (default `nats://127.0.0.1:4222`). Run via:

    docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d nats
    pytest tests/integration/test_nats_latency.py -v

Acceptance: round-trip publish→consume p95 < 50ms.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
import uuid

import pytest

pytest.importorskip("nats")

NATS_URL = os.environ.get("ABS_NATS_URL", "nats://127.0.0.1:4222")
SAMPLE_COUNT = 200
PCT95_BUDGET_MS = 50.0


async def _broker_reachable() -> bool:
    import nats

    try:
        nc = await asyncio.wait_for(nats.connect(NATS_URL), timeout=2.0)
    except Exception:
        return False
    await nc.close()
    return True


@pytest.fixture(scope="module")
def _require_broker() -> None:
    if not asyncio.run(_broker_reachable()):
        pytest.skip(f"NATS broker not reachable at {NATS_URL}")


async def test_jetstream_pubsub_latency_p95_under_50ms(_require_broker) -> None:
    import nats
    from nats.js.api import RetentionPolicy, StreamConfig
    from nats.js.errors import BadRequestError

    stream = f"ABS_T001_{uuid.uuid4().hex[:8].upper()}"
    subject = f"abs.t001.{uuid.uuid4().hex[:8]}"

    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()

    cfg = StreamConfig(
        name=stream,
        subjects=[subject],
        retention=RetentionPolicy.LIMITS,
        max_msgs=SAMPLE_COUNT * 4,
    )
    try:
        await js.add_stream(cfg)
    except BadRequestError:
        await js.update_stream(cfg)

    received: asyncio.Queue[float] = asyncio.Queue()

    async def handler(msg) -> None:  # noqa: ANN001
        await received.put(time.perf_counter())
        await msg.ack()

    sub = await js.subscribe(subject, cb=handler, manual_ack=True)

    samples_ms: list[float] = []
    try:
        for _ in range(SAMPLE_COUNT):
            t0 = time.perf_counter()
            await js.publish(subject, b"x")
            t1 = await asyncio.wait_for(received.get(), timeout=2.0)
            samples_ms.append((t1 - t0) * 1000.0)
    finally:
        await sub.unsubscribe()
        try:
            await js.delete_stream(stream)
        except Exception:
            pass
        await nc.drain()
        await nc.close()

    p50 = statistics.median(samples_ms)
    p95 = statistics.quantiles(samples_ms, n=20)[18]  # 95th percentile

    print(
        f"\nsamples={len(samples_ms)} p50={p50:.2f}ms p95={p95:.2f}ms "
        f"max={max(samples_ms):.2f}ms"
    )

    assert p95 < PCT95_BUDGET_MS, (
        f"JetStream round-trip p95 {p95:.2f}ms exceeds {PCT95_BUDGET_MS}ms budget"
    )
