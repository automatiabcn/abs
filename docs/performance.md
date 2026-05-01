# Performance Benchmarks

Last run: **2026-04-27** — Hardware: Apple M-series (geliştirme makinesi, üretim
VPS Hetzner CX22 = 1 vCPU + 2 GB RAM benchmark karşılığı için aşağıdaki sayıları
2-3× yavaş kabul edebilirsin).

Her benchmark `benchmarks/` klasöründe — `python benchmarks/<name>.py` ile çalışır.
CI haftalık koşar: `.github/workflows/benchmarks.yml`.

---

## 1. Cascade Latency (locust load test)

**Senaryo:** 100 concurrent user, spawn rate 10/s, 5 dakika sustained, endpoint
`POST /v1/cascade/ask`. wait_time `between(0.1, 0.5)`.

**Beklenen p99:** < 1000 ms (Groq ortalama 300 ms, fail-over Cerebras +200 ms).

| Metrik | Hedef | Notlar |
|---|---|---|
| Throughput | 80-100 req/s sustained | Free tier provider quota (Groq 6000 TPM) |
| p50 latency | 300-400 ms | Groq baseline |
| p95 latency | 700-900 ms | Cerebras failover dahil |
| p99 latency | < 1000 ms | Cohere/CF failover |
| Error rate | < 1% | rate_limited 429 retry |

**Çalıştırma:**
```bash
locust -f benchmarks/cascade_load.py --host http://localhost:8000 \
       --users 100 --spawn-rate 10 --run-time 5m \
       --html benchmarks/results/01_cascade_load.html \
       --csv benchmarks/results/01_cascade_load --headless
```

> **Not:** Locust live backend gerektirir; bu repo'daki run lokal scenario JSON üretmektedir.

---

## 2. Vault Decrypt Overhead (sops + age)

**Beklenen:** Boot'ta 1 kez decrypt, < 100 ms. Runtime'a etki yok.

| Metrik | Ölçüm | Hedef |
|---|---|---|
| Mean | < 50 ms | sops + age 4096-bit |
| Median | < 50 ms | — |
| Max | < 100 ms | dosya boyutu artarsa lineer |

**Last run (simulate, sops yok):** mean 0.027 ms, p95 0.032 ms (kriptolu okuma
proxy benchmark). Gerçek sops + age kurulu sistemde mean 30-60 ms beklenir.

---

## 3. Symbol Graph Indexing (10K+ LOC)

**Hedef:** `core/backend/app` (12.5K LOC, 156 dosya) altında symbol parser çalışsın
ve sembol grafiğini SQLite'a yazsın.

**Last run (lokal):**

| Metrik | Değer |
|---|---|
| Files | 156 |
| LOC | 12 521 |
| Symbols | 1 932 |
| Elapsed | **0.263 s** (~ms/dosya 1.69) |
| Memory peak | 1.78 MB |
| Throughput | ~47 K LOC/saniye |

**VPS extrapolation:** Hetzner CX22 (1 vCPU 2.5 GHz) ~3× yavaş → 0.8 s tahmini,
hâlâ 60 s threshold'un çok altında.

---

## 4. Watchdog Resource Sample (psutil)

**Senaryo:** Watchdog process 10 dakika çalıştır, her 10 sn psutil sample.
CI'da daha kısa: 60 s, her 5 sn.

**Last run (20 sn quick run, geliştirme makinesi):**

| Metrik | Değer | Hedef |
|---|---|---|
| Sample count | 5 | — |
| RSS mean | 15.7 MB | < 200 MB |
| RSS max | 15.7 MB | < 200 MB |
| CPU % mean | 0.0% | < 5% |
| CPU % max | 0.0% | < 5% |
| Threads | 1 | — |

VPS'te uzun süreli watchdog scanning + alerter eklenince RSS 50-100 MB seviyesinde
beklenir; her halükarda hedeflerin altında.

---

## Trend (haftalık CI)

`.github/workflows/benchmarks.yml` her Pazartesi 03:00 UTC çalışır → sonuçlar
`benchmarks/results/` artifact olarak yüklenir. Son 4 haftalık trend `perf_summary`
MCP tool ile incelenebilir:

```bash
ask "perf_summary" gptoss
```

Beklenen JSON: `{cascade, vault, symbol, watchdog, last_run}`. Eğer bir
benchmark > %20 yavaşladıysa CI alert tetikler (022+'a deferred).

---

## Yöntemoloji notları

- Locust senaryosu **CPU-bound testtir** — gerçek müşteri ABS'i Claude Code
  client'ından çağırır, locust HTTP overhead'i ekler. Gerçek client p99'u
  bizimkinden ~50-100 ms daha düşük olabilir.
- Vault decrypt benchmark sops binary kuruluyken ölçülmeli — simulated mode
  alt sınırı verir (kript hash hızı).
- Symbol indexing tek thread; multi-process indexing 022+'a planlandı (10×
  hızlanma beklentisi).
- Watchdog VPS'te uzun süreli (24 sa) çalıştırılmalı — kısa sample'lar memory
  leak'i yakalamaz.

Daha detaylı bilgi: [Architecture](architecture.md), [Operations](operations.md).
