# Performance Benchmarks

Last run: **2026-04-27** — Hardware: Apple M-series development machine. For a
production VPS (Hetzner CX22 = 1 vCPU + 2 GB RAM) assume the numbers below are
2-3× slower.

Every benchmark lives in `benchmarks/` — run it with `python benchmarks/<name>.py`.
CI runs them weekly: `.github/workflows/benchmarks.yml`.

---

## 1. Cascade Latency (locust load test)

**Scenario:** 100 concurrent users, spawn rate 10/s, 5 minutes sustained, endpoint
`POST /v1/cascade/ask`. wait_time `between(0.1, 0.5)`.

**Expected p99:** < 1000 ms (Groq averages 300 ms, failing over to Cerebras adds +200 ms).

| Metric | Target | Notes |
|---|---|---|
| Throughput | 80-100 req/s sustained | Free tier provider quota (Groq 6000 TPM) |
| p50 latency | 300-400 ms | Groq baseline |
| p95 latency | 700-900 ms | including Cerebras failover |
| p99 latency | < 1000 ms | Cohere/CF failover |
| Error rate | < 1% | rate_limited 429 retry |

**Run it:**
```bash
locust -f benchmarks/cascade_load.py --host http://localhost:8000 \
       --users 100 --spawn-rate 10 --run-time 5m \
       --html benchmarks/results/01_cascade_load.html \
       --csv benchmarks/results/01_cascade_load --headless
```

> **Note:** Locust needs a live backend; the run committed in this repository produces a local scenario JSON instead.

---

## 2. Vault Decrypt Overhead (sops + age)

**Expected:** decrypted once at boot, < 100 ms. No runtime impact.

| Metric | Measurement | Target |
|---|---|---|
| Mean | < 50 ms | sops + age 4096-bit |
| Median | < 50 ms | — |
| Max | < 100 ms | grows linearly with file size |

**Last run (simulated, sops not installed):** mean 0.027 ms, p95 0.032 ms (a proxy
benchmark for encrypted reads). On a real system with sops + age installed, expect
a mean of 30-60 ms.

---

## 3. Symbol Graph Indexing (10K+ LOC)

**Target:** run the symbol parser over `core/backend/app` (12.5K LOC, 156 files)
and write the symbol graph to SQLite.

**Last run (local):**

| Metric | Value |
|---|---|
| Files | 156 |
| LOC | 12 521 |
| Symbols | 1 932 |
| Elapsed | **0.263 s** (~1.69 ms/file) |
| Memory peak | 1.78 MB |
| Throughput | ~47 K LOC/second |

**VPS extrapolation:** a Hetzner CX22 (1 vCPU, 2.5 GHz) is ~3× slower → an estimated
0.8 s, still far below the 60 s threshold.

---

## 4. Watchdog Resource Sample (psutil)

**Scenario:** run the watchdog process for 10 minutes, taking a psutil sample every
10 s. Shorter in CI: 60 s, sampled every 5 s.

**Last run (20 s quick run, development machine):**

| Metric | Value | Target |
|---|---|---|
| Sample count | 5 | — |
| RSS mean | 15.7 MB | < 200 MB |
| RSS max | 15.7 MB | < 200 MB |
| CPU % mean | 0.0% | < 5% |
| CPU % max | 0.0% | < 5% |
| Threads | 1 | — |

Once watchdog scanning and the alerter run for long stretches on a VPS, expect RSS
in the 50-100 MB range — still under the targets.

---

## Trend (weekly CI)

`.github/workflows/benchmarks.yml` runs every Monday at 03:00 UTC → results are
uploaded to `benchmarks/results/` as artifacts. The last 4 weeks of trend data can
be inspected with the `perf_summary` MCP tool:

```bash
ask "perf_summary" gptoss
```

Expected JSON: `{cascade, vault, symbol, watchdog, last_run}`. A CI alert on any
benchmark that regresses by more than 20% is deferred to a later release.

---

## Methodology notes

- The locust scenario is a **CPU-bound test** — a real customer calls ABS from the
  Claude Code client, whereas locust adds its own HTTP overhead. The p99 a real
  client sees may be ~50-100 ms lower than ours.
- The vault decrypt benchmark should be measured with the sops binary installed —
  simulated mode only gives the lower bound (the speed of the crypto hash).
- Symbol indexing is single-threaded; multi-process indexing is planned for a later
  release (expected 10× speedup).
- The watchdog should be run on a VPS for a long stretch (24 h) — short samples will
  not catch a memory leak.

For more detail: [Architecture](architecture.md), [Operations](operations.md).
