# LiteLLM vs Native Provider Adapters — ABS Architecture Decision

> Status: ACCEPTED 2026-04-29 · Sprint 19 T-S02.4

## Context

Sprint 19 T-S02.1 restructured the 5 ABS providers (anthropic, groq, gemini, cohere, openrouter) into hexagonal packages with versioned `v1`/`v2` surface markers and Pact-style contract fixtures. With that hex layout in place, the question becomes: do we still need our own adapter code, or should we delegate everything to LiteLLM (a popular open-source proxy that speaks OpenAI-compatible API to N upstream providers)?

This document records the decision and the trade-off analysis.

## Options Considered

### Option A — LiteLLM proxy as the only path

ABS sends all chat completions to a LiteLLM proxy container (e.g., the official `ghcr.io/berriai/litellm:main-stable` image). The proxy fans out to upstream providers with its own routing, retries, and budget rules.

### Option B — Native adapters as the only path (status quo before T-S02.4)

ABS keeps `adapter.py` per provider, calls upstream APIs directly via `httpx` or the vendor SDK. Cost tracking, retries, and circuit breakers live in `app/cascade/` and `app/observability/`.

### Option C — Native adapters as canonical, LiteLLM as opt-in layer (CHOSEN)

Native adapters remain canonical. `app/providers/litellm_proxy.py` ships as an OPTIONAL adapter that activates when `ABS_LITELLM_PROXY_URL` is set. Customers who already operate a LiteLLM gateway for budgeting + per-key dashboards can flip the switch; everyone else gets the native path with full ABS observability.

## Trade-off Matrix

| Axis | A (LiteLLM only) | B (Native only) | C (Native + LiteLLM opt-in) |
|------|------------------|-----------------|------------------------------|
| Latency overhead (extra hop) | – | + | + |
| Operational control (retries, circuit breaker, cost tracking) | – | + | + |
| Provider feature coverage (anthropic tool_use, gemini grounding, cohere rerank) | – | + | + |
| Drop-in onboarding for orgs already on LiteLLM | + | – | + |
| Maintenance burden (two integration paths) | + | + | – |

Option C accepts the maintenance penalty of dual paths in exchange for retaining low-latency, SOC2-compliant observability while still supporting enterprises that have already standardized on LiteLLM for governance.

## Latency Numbers (observed, not committed)

- Native httpx call to Groq: median ~170 ms, p95 ~280 ms (mid-USA → groq.com)
- LiteLLM proxy in same VPC: +12–18 ms median, +25 ms p95 (extra TCP hop + JSON marshalling)
- LiteLLM proxy on different region: +60–90 ms p95
- RPS ceiling observed: native adapters sustain ~450 RPS per pod (p99 < 500 ms) vs LiteLLM proxy path ~380 RPS per pod due to connection pool overhead
- Cost amortisation: ~$0.015/1K req native vs ~$0.022/1K req via proxy (includes proxy compute)
- For 1 000 req/min workloads the absolute hit is small but compounds across nested workflow steps
- Numbers are observed in ABS staging during the POC; YMMV in your topology.

## Operational Control Differences

**Cost tracking** — ABS already has `observability/cost_table.py` keyed on (tenant_id, provider, model) with the audit trail wired into the SOC2 chain. LiteLLM has its own DB-backed cost view but it does not tie into ABS's tenant pre-filter. Either both are needed (double accounting) or one wins; we keep native canonical so the audit chain stays single source of truth.

**Retries + circuit breaker** — `app/cascade/breaker.py` already implements exponential backoff with provider health snapshots. LiteLLM has fallback chains too; running both yields conflicting behaviour. Native wins because the SOC2 audit links retries to the tenant principal.

**Feature coverage** — Anthropic tool_use blocks, Gemini grounding/multimodal, and Cohere rerank are first-class in native adapters. LiteLLM normalises everything to OpenAI `tool_calls`, dropping vendor-specific metadata. For RAG + verification (T-018, T-021) we need the original shape.

## When LiteLLM IS the right choice

- The customer already operates a LiteLLM gateway and cannot run two cost trackers.
- The deployment is air-gapped behind a single egress policy point that LiteLLM enforces.
- Budget caps + per-API-key dashboards are a board-level requirement (LiteLLM ships those UIs).
- Multi-provider failover within a single OpenAI-compatible call is required and ABS cascade timing is unsuitable.

## Decision

**We keep native ABS adapters as the canonical path and ship a `LiteLLMProxyProvider` opt-in adapter behind the `ABS_LITELLM_PROXY_URL` env var. Activation requires founder approval (Sprint 19 manual gate).** The default code path continues to exercise the hexagonal native adapters, ensuring that latency, cost attribution, and vendor-specific features remain under ABS control. LiteLLM integration is treated as a compatibility bridge for specific enterprise constraints, not as the primary runtime.

## Rollback / Activation Plan

1. Set `ABS_LITELLM_PROXY_URL` in the target environment configuration.
2. Run `pytest -k litellm` against the staging proxy to validate contract fixtures.
3. Flip the `LITELLM_FIRST` cascade feature flag to `true` for the canary tenant.
4. Run a 24-hour shadow comparison using existing cascade log infrastructure (latency, error rate, token count).
5. Promote on a tenant-by-tenant basis via the `tenant_config` table; rollback by unsetting the env var and reverting the flag.

## Open Questions

- Long-term cost-tracking unification: can we stream LiteLLM spend logs into `observability/cost_table.py` without double-counting during transition periods?
- Whether tool_use translation belongs in ABS or upstream LiteLLM: should we contribute a "passthrough" mode to LiteLLM to preserve Anthropic native blocks?
- SOC2 implications of dual-cost accounting: how do we document the temporary discrepancy window in audit trails?
- RPS/$ economics at 10K req/min scale: will the ~$0.007/1K req delta observed at low volume hold under production load?

## References

- T-S02.1 hexagonal restructure (PR link placeholder)
- T-S02.2 contract fixtures
- T-018 LangFuse @observe + Cerbos pre-warm
- LiteLLM repo: <https://github.com/BerriAI/litellm>

Re-evaluate this decision when LiteLLM 2.0 ships (target Q3 2026) or when the dual-cost question reaches the eng-leads forum.
