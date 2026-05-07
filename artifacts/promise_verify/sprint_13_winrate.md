# Sprint 13 multi-model win-rate evidence
> Generated: 2026-05-07T11:53:50+00:00 · mode: `offline` · duration: 0.0s
> Dataset: `core/backend/tests/fixtures/golden_eval_multimodel.json` (3 rows)
> GPT-OSS model: `openai/gpt-oss-120b`
> Claude model: `claude-opus-4-1-20250805`

## Aggregate
| Bucket | Count |
|---|---|
| gpt_oss_wins | 0 |
| claude_wins | 0 |
| tie | 0 |
| claude_unavailable | 0 |
| skipped | 0 |
| error | 3 |

**Win-rate: unmeasured** — no head-to-head pairs were judged.

## First five non-trivial rows
_No rows judged — see `claude_unavailable` count above._

## How to reproduce

```bash
# Requires GROQ_API_KEY (free) + ANTHROPIC_API_KEY (paid opt-in).
python scripts/eval/multimodel_winrate.py
```
