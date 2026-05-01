# Landing Page Hero A/B Test (`landing_hero_v1`)

A/B test on the homepage hero during launch week.

**Owner:** `@ops` · **Tool:** GrowthBook · **Flag:** `landing_hero_v1` · **Allocation:** 25 % per variant.

---

## Hypothesis

Leading with a specific user pain (cost), tangible outcome (RAG in 30 min), or trust signal (GDPR) will outperform our current feature-led headline on click-through to `/pricing`. Visitors respond better to a concrete benefit or a direct solution to a pain than to a list of features.

## Variants

| Variant | Type | Headline (H1) | Sub-headline |
|---|---|---|---|
| **V_A** | Control / feature-led | 75 MCP tools and 6-provider cascade | The self-hosted AI orchestration server. Yours forever for a $299 one-time payment. |
| **V_B** | Pain-led / cost | Stop paying $1,000/month for AI tools you can self-host | 110+ tools, RAG, and multi-tenancy. $299 one-time. |
| **V_C** | Outcome-led / time-to-value | Run RAG on your own server in 30 minutes | The self-hosted AI orchestration platform with RAG built-in. $299 one-time. |
| **V_D** | Trust-led / compliance | GDPR-compliant AI orchestration. Yours forever, $299. | Self-host your AI stack with a platform built in the EU. Own your data and your tools. |

## Success metric

- **Primary:** click-through rate (CTR) on the hero CTA → `/pricing`.
- **Goal:** ≥ 10 % lift over control, statistically significant.

## Sample size + duration

- α = 0.05, power = 0.80, baseline CTR ≈ 4 %.
- ~800 conversions per variant to detect a 10 % relative lift.
- Stop conditions:
  1. 7 days elapsed, OR
  2. p < 0.05 AND ≥ 800 conversions on the leading variant.

## Decision rule

- If a variant wins, promote to 100 % traffic on T+8d.
- If no variant wins, keep V_A and re-test with stronger hypothesis copy in 30 days.
- If V_B or V_C wins but lift < 10 %, hold the test open another 7 days only if the cost of running it stays below 0.5 % of paid conversions.
