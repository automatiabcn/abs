# Customer Journey — API Key Checklist

> Free-tier by default. Goal: 100 % free path by default; Claude / Recall / ElevenLabs are opt-in only.

## Required (free tier)

These keys are mandatory for the standard customer-journey playthrough. All four come with generous free quotas.

| Var | Provider | Purpose | Free quota |
|-----|----------|---------|------------|
| `GROQ_API_KEY` | Groq | LLM (Llama 3.3 70B, GPT-OSS-120B, Kimi K2, Qwen3-32B, Llama 4 Scout) | 1M tokens/day per model |
| `CF_API_KEY` + `CF_ACCOUNT_ID` | Cloudflare Workers AI | LLM fallback + image gen | 10K neurons/day |
| `TEST_GEMINI_API_KEY` | Google AI Studio | Gemini 2.5 Flash/Pro for templates + multimodal | 1.5K req/day Flash |
| `TEST_GMAIL_OAUTH_CLIENT_ID` + `TEST_GMAIL_OAUTH_CLIENT_SECRET` | Google Cloud Console | Gmail integration in the workflow nodes | 1M req/day |

## Optional (opt-in, paid)

These trigger paid SaaS behaviour and stay disabled by default. Each has an enable-flag env var so the user explicitly turns them on.

| Var | Enable flag | Purpose | Notes |
|-----|-------------|---------|-------|
| `ABS_ANTHROPIC_API_KEY` | `ABS_ANTHROPIC_ENABLED=true` | Claude Plus quota-test | Quota tracker enforces 80 % warn / 95 % block |
| `ABS_RECALL_AI_API_KEY` | `ABS_RECALL_ENABLED=true` | Recall.ai meeting bot (~$0.50/hr) | Free path uses meetily/jitsi |
| `ABS_ELEVENLABS_API_KEY` | `ABS_ELEVENLABS_ENABLED=true` | ElevenLabs TTS | Free path uses Coqui XTTS-v2 / Piper |

## Removed from the journey

The following keys appeared in earlier journey docs but are no longer required (paid SaaS replaced by free local equivalents):

- ❌ `TEST_OPENAI_API_KEY` — covered by Groq + CF + Gemini for free.
- ❌ `TEST_ANTHROPIC_API_KEY` — moved to opt-in (see above).
- ❌ `TEST_RECALL_API_KEY` — replaced by the meetily/jitsi self-host path.
- ❌ `TEST_ELEVENLABS_API_KEY` — replaced by Coqui + Piper.

## Verifying the free path

1. Run `python scripts/seed_demo_tenant.py` — should emit `WROTE … fingerprint=…`.
2. Run the customer journey through Phase 6 (`/admin/usage` widget) — Claude budget must read `0 %` on first use.
3. Switch the workflow builder to a template and click Synthesize — synthesis runs entirely on Groq + CF; no `anthropic.com` traffic in the egress log.

## Audit

Every opt-in flag flip is logged to the SOC2 audit chain. Setting `ABS_ANTHROPIC_ENABLED=true` writes a `quota.opt_in` audit row with the operator's principal id; flipping it back writes `quota.opt_out`. Keep these in mind during a customer-journey playthrough — they show the gate is real.
