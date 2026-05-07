# ADR-002 — LiteLLM Proxy: Native Canonical, Opt-In Layer

| | |
|---|---|
| Status | **ACCEPTED** |
| Date | 2026-04-29 |
| Sprint | 19 (post-completion gate G2) |
| Deciders | Automatia BCN engineering |
| Supersedes | – |
| Superseded by | – |
| References | [`litellm-vs-native.md`](./litellm-vs-native.md), T-S02.1, T-S02.4, T-018 |

## Context

Sprint 19 T-S02.4 evaluated routing every LLM call through a LiteLLM proxy versus keeping ABS's own provider adapters as the canonical path. The trade-off document covers the matrix in detail; this ADR records the formal decision so it is unambiguous in future audits and onboarding.

ABS today ships **17 native provider integrations** (5 hex-restructured in T-S02.1 + 12 cascade providers) that are production-tested with Cerbos pre-filter, LangFuse `@observe` traces, T-018 cost table, and the T-016 SOC2 audit chain. LiteLLM is a popular open-source gateway that speaks an OpenAI-compatible API to many upstream providers and ships its own budget UIs.

## Decision

**ABS keeps native provider adapters as the canonical execution path. LiteLLM is supported as an OPT-IN proxy layer activated by setting `ABS_LITELLM_PROXY_URL`.**

This corresponds to **Option C** in the trade-off matrix.

The `LiteLLMProxyProvider` class in `app/providers/litellm_proxy.py` ships in mainline code so customers can flip the env var without a redeploy, but no default routing exists. Activation requires founder approval per Sprint 19's manual-gate list.

## Rationale

1. **Latency.** Native httpx call to Groq median ~170 ms; LiteLLM proxy in same VPC adds 12–18 ms median (+25 ms p95). Across nested workflow steps (T-S03.1 templates frequently chain 3–5 nodes) the proxy hop compounds.
2. **Operational control.** ABS already owns the cost table (`observability/cost_table.py`), retry / circuit breaker (`cascade/breaker.py`), and audit chain (T-016). Routing through LiteLLM creates dual-cost accounting and a second retry policy, which break SOC2 single-source-of-truth invariants.
3. **Provider feature coverage.** Anthropic tool_use, Gemini grounding/multimodal, and Cohere rerank are first-class in our adapter.py modules. LiteLLM normalises everything to OpenAI `tool_calls` and drops vendor metadata that ABS RAG verification (T-021) depends on.
4. **Drop-in onboarding for LiteLLM-standardised orgs.** The opt-in adapter avoids a binary "use ABS or LiteLLM" choice — orgs already running LiteLLM gateways for budget UIs can flip the env var with no migration.
5. **Maintenance burden.** Dual paths cost some test coverage and CI minutes; we accept this in exchange for #1–#4.

## Consequences

### Positive

- ABS retains end-to-end observability and SOC2 audit single-source-of-truth.
- Latency tail-p95 stays low for chained workflow runs.
- Vendor-specific features (tool_use blocks, grounding, rerank) keep working.
- LiteLLM-standardised customers can integrate with one env var.

### Negative / Accepted Trade-offs

- Two integration paths to maintain (mitigated: `LiteLLMProxyProvider` reuses the OpenAI-compatible helper; surface area is a single adapter file).
- When LiteLLM is enabled by a customer, ABS observability captures the proxy hop only — upstream provider attribution becomes coarser.
- LiteLLM 2.0 may introduce features (passthrough mode, native tool_use) that change the calculus; this ADR has a re-review trigger (see below).

## Implementation State

- ✅ `app/providers/litellm_proxy.py` — opt-in adapter (`is_enabled()` reads `ABS_LITELLM_PROXY_URL`).
- ✅ `docs/architecture/litellm-vs-native.md` — trade-off matrix + activation runbook.
- ✅ This ADR.
- ⏸️ No default cascade routing through LiteLLM. Activation per-tenant requires founder sign-off.

## Re-Review Triggers

Re-open this decision when **any** of:

1. LiteLLM 2.0 ships (target Q3 2026) with native passthrough for vendor-specific tool_use blocks.
2. A customer-driven requirement makes per-API-key budget UIs non-negotiable for >25 % of revenue.
3. The cost-table + audit chain unification question reaches the eng-leads forum.
4. Latency overhead of the opt-in path drops below 5 ms p95 (commodity-priced sidecars, etc.).

## Sign-off

| Role | Name | Decision | Date |
|------|------|----------|------|
| Founder / Approver | Automatia BCN engineering | ✅ Accepted (Option C — native canonical, LiteLLM opt-in) | 2026-04-29 |
| Engineering | ABS platform team | ✅ Implemented as designed | 2026-04-29 |

This ADR is the controlling document; the trade-off doc is informational background.
