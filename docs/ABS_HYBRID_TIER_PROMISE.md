# ABS Hybrid Tier Promise

> v1.0 · 2026-04-29 · Sprint 20 T-F04

## What ABS guarantees

If a customer pays **$20 / month for a Claude Plus subscription** and runs ABS on their own server, ABS keeps total monthly spend at the floor of:

- **Subscription:** $20 (Claude Plus)
- **Compute:** their own hardware (sunk cost)
- **Everything else ABS does:** $0

## Why this works

| Layer | Free provider | Paid alternative |
|-------|---------------|------------------|
| LLM heavy reasoning | Groq GPT-OSS-120B | Claude Opus / Sonnet (opt-in) |
| LLM general | Groq Llama 3.3 70B, Llama 4 Scout, Kimi K2, Qwen3-32B | Claude Haiku |
| Cloud LLM fallback | Cloudflare Workers AI (Kimi K2.5 256K, Llama 4 Scout, GPT-OSS) | OpenAI / Anthropic |
| Multimodal | Gemini 2.5 Flash/Pro | OpenAI Vision |
| Local LLM | Ollama (Phi-4, Gemma-2, Qwen 2.5 Coder, CodeLlama, Llava) | – |
| Embedding | Cohere `embed-english-v3.0` (free tier) + Ollama BGE | OpenAI text-embedding-3 |
| Reranker | Cohere `rerank-multilingual-v3.0` (free tier) + Qwen3 ONNX local | – |
| Meeting bot | meetily / jitsi self-host + WhisperX local | Recall.ai (~$0.50/hr) |
| TTS | Coqui XTTS-v2 + Piper | ElevenLabs (~$0.0006/char) |
| Vector DB | Qdrant self-host | Pinecone |
| Observability | LangFuse self-host | LangSmith |
| Workflow engine | Inngest dev mode + n8n self-host | Inngest cloud |

## How ABS spends Claude responsibly

When the customer opts into Claude (`ABS_ANTHROPIC_ENABLED=true` + their own `ABS_ANTHROPIC_API_KEY`):

1. **Free path first.** ABS quality pipelines (`qual_code`, `qual_analysis`, `race_code`, `cascade`) all default to Groq + Cloudflare + Gemini + Cohere + Ollama. None of those paths touch Anthropic.
2. **Quota tracker.** `app/observability/quota_monitor.py` records every Claude token to a monthly ledger. Two thresholds:
   - **80 %** → warning banner on `/admin/usage`, LangFuse trace tagged `claude_budget_warn`.
   - **95 %** → hard block (`QuotaExceeded`), automatic fallback to Groq.
3. **Pre-flight gate.** Before each Claude call, the adapter projects `used + max_tokens` and refuses up-front if that breaches 95 %.
4. **No silent overruns.** If the user's monthly token budget would be exceeded mid-run, the call returns a `ProviderError` and the cascade picks the next provider; the customer never sees a Claude bill they did not budget for.

## Quality bar

Sprint 13 multi-model ensemble (T-049..T-056) verified that GPT-OSS-120B baseline answers reach ≥50 % win-rate against Claude Opus on the golden eval set. ABS's "best-free verified" badge replaces the legacy "premium" badge — same quality, no recurring cost.

## What the customer sees

- **`/admin/usage` widget**: real-time `Free path: X %` + `Claude budget: Y %`.
- **LangFuse dashboard**: `claude_tokens_used_pct_month` time-series.
- **Audit chain**: every opt-in flip and quota-block event written to the T-016 SOC2 audit log.
- **Workflow canvas (T-S03.4)**: `Estimated cost per run: $X.XX` shows zero for free-tier-only workflows.

## Promise summary (one paragraph)

ABS lets the customer keep their Claude Plus subscription as a fixed-cost premium lane while doing 95 %+ of the work on free providers. The quota monitor enforces the monthly budget so a runaway workflow can never burn through the customer's Claude allowance. ABS-specific quality features (qual_code, race_code, cascade, RAG, judge) all run on free providers by default. Total cost: $20 + sunk-cost compute. No surprises.

## Sign-off

> Author: Founder + ABS engineering · Sprint 20 T-F04 · 2026-04-29.
