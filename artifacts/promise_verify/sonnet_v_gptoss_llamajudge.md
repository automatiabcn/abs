# Sprint 13 multi-model win-rate evidence
> Generated: 2026-05-05T22:52:15+00:00 · mode: `live` · duration: 328.1s
> Dataset: `core/backend/tests/fixtures/golden_eval_multimodel.json` (30 rows)
> GPT-OSS model: `openai/gpt-oss-120b`
> Claude model: `claude-sonnet-4-5-20250929`

## Aggregate
| Bucket | Count |
|---|---|
| gpt_oss_wins | 24 |
| claude_wins | 6 |
| tie | 0 |
| claude_unavailable | 0 |
| skipped | 0 |
| error | 0 |

**GPT-OSS-120B win-rate (vs Claude claude-sonnet-4-5-20250929, contested 30/30): 80.0 %**

## First five non-trivial rows
| id | category | verdict | error |
|---|---|---|---|
| code-01 | code | gpt_oss_wins | - |
| code-02 | code | gpt_oss_wins | - |
| code-03 | code | claude_wins | - |
| code-04 | code | gpt_oss_wins | - |
| code-05 | code | gpt_oss_wins | - |

## How to reproduce

```bash
# Requires GROQ_API_KEY (free) + ANTHROPIC_API_KEY (paid opt-in).
python scripts/eval/multimodel_winrate.py
```
