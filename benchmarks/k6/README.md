# T-059 — k6 Load Tests

Three scenarios in one script: smoke (1 VU / 30s), constant 100 RPS for 5 min, and a 1000-concurrent ramp.
The script runs against staging — never production.

## Targets

| Metric | Budget |
|---|---|
| Overall `http_req_duration` p99 | < 500 ms |
| RAG `rag_query_p99` | < 500 ms |
| Meeting upload p99 | < 2000 ms |
| Status report p99 | < 1500 ms |
| News digest p99 | < 1000 ms |
| Email draft p99 | < 800 ms |
| `http_req_failed` rate | < 0.1 % |
| Custom `errors` rate | < 0.1 % |

## Run

```
k6 run \
  -e ABS_BASE_URL=https://staging.abs-server.example.com \
  -e ABS_TOKEN=<bearer> \
  -e ABS_AUDIENCE=abs-mcp \
  benchmarks/k6/abs_load.js
```

JSON summary lands at `benchmarks/results/k6_summary.json`.

## CI

`.github/workflows/k6-weekly.yml` runs the script weekly (Sunday 02:00 UTC) against
staging, uploads the summary as an artifact, and fails the job if any threshold breaches.
