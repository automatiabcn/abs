# API Reference — MCP Tools
This page is generated automatically (`python scripts/gen_api_reference.py`). Do not edit it by hand.
**104 tools** in total — grouped by category, alphabetical within each.
After `claude mcp add abs <url>`, every MCP tool is callable from Claude Code as `mcp__abs__<tool>`, or through the orchestrator aliases (`ask "..." gptoss`, etc.).

## System & Health

_38 tools_

### `apply_patch`
Apply a unified diff (atomic + backup). Returns a reason if the rollback fails.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `file_path` | `string` | ✓ |  |
| `unified_diff` | `string` | ✓ |  |
| `backup` | `boolean` |  |  |

### `auto_verify_code`
Parallel code verification on the local GPU — granite-2b security + codellama tests + deepseek lint.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `code` | `string` | ✓ |  |

### `auto_verify_turkish`
Quality check for Turkish text — grammar and style via aya-8b.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `text` | `string` | ✓ |  |

### `billing_status`
ABS billing dashboard: Stripe + database licence + the last 10 webhook events.

### `breaker_status`
Circuit breaker states for the provider chain (open/half_open/closed).

### `cache_stats`
Semantic cache statistics (hit/miss/entries/hit_rate).

### `code_fingerprint`
Fingerprint for a piece of code: SHA-256 + line/function counts + basic metrics.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `code` | `string` | ✓ |  |

### `code_review`
Code review — tier chosen automatically (quick <50 lines, standard 50-200, exhaustive 200+).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `code` | `string` | ✓ |  |
| `tier` | `string` |  |  |

### `daily_cost`
tracker × provider_configs pricing → estimated cost for today.

### `demo_status`
Demo countdown state (started/expired/days_remaining).

### `email_queue_status`
ABS onboarding email queue dashboard.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

### `freeze`
Turn on freeze mode: allow Write/Edit only inside the given directory.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `project_dir` | `string` |  |  |

### `health_status`
Real-time ping status for every provider.

### `humanize_score`
Heuristic 'AI-written' score for the input text (0=human, 1=AI). Returns JSON.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `text` | `string` | ✓ |  |

### `investigate`
Investigate mode — turn on root-cause investigation. Hooks emit warnings.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `topic` | `string` |  |  |

### `judge_outcome`
Mark the outcome of a judgment (accept|reject).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `judgment_id` | `string` | ✓ |  |
| `outcome` | `string` |  |  |

### `judge_patch`
SENIOR JUDGE — combined diff AST + LLM score. 60% fingerprint + 40% LLM.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `unified_diff` | `string` | ✓ |  |
| `file_path` | `string` |  |  |

### `judge_persona_predict`
Predict the accept probability of these scores with the ML model.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `ast_score` | `number` | ✓ |  |
| `llm_score` | `number` | ✓ |  |
| `persona_drift` | `number` | ✓ |  |

### `judge_persona_reset`
Reset the persona back to DEFAULT_PERSONA (the history file is preserved).

### `judge_persona_status`
Current persona thresholds + last training metadata + history size.

### `judge_persona_train`
Dynamically adjust the persona from judge_log outcomes. Returns 'insufficient_data' below min_samples.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `min_samples` | `integer` |  |  |

### `judge_recent`
The last N judgment records (id, ts, file, ast/llm/combined, outcome).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

### `judge_stats`
Judgment averages for the last N days + drift_signal + outcome_counts + top_files.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `window_days` | `integer` |  |  |

### `learnings_log`
Add a learning manually. category: bugfix|delegation|arch|security|perf|ux.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `category` | `string` | ✓ |  |
| `lesson` | `string` | ✓ |  |
| `project` | `?` |  |  |

### `learnings_recent`
The last N learning records + statistics per category.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

### `license_status`
ABS licence + demo state snapshot — returns JSON.

### `model_health`
Simple model health score, derived from the circuit breaker state.

### `preview_patch`
Apply a unified diff as a dry run; returns success + reason.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `file_path` | `string` | ✓ |  |
| `unified_diff` | `string` | ✓ |  |

### `quota_status`
Provider quota state (circuit breaker state snapshot).

### `score_patch_quality`
Score a patch 0-10 on minimalism + hunk concentration.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `unified_diff` | `string` | ✓ |  |

### `setup_status`
Current state of the customer setup wizard — returns JSON.

### `system_status`
ABS system status — licence, provider circuit breaker state, cache, tool usage.

### `update_check`
Remote release manifest → version compare → state JSON.

### `vault_status`
Vault snapshot — list of configured keys + the last 5 audit events. No cleartext.

### `workflow_resume`
Return the state a workflow can resume from, starting at its last successful step.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `trace_id` | `string` | ✓ |  |

### `workflow_status`
Workflow durability snapshot — total, by_status, last 5 + db_size_kb.

### `write_docs`
Turkish API documentation (markdown) for a module or function.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `module_info` | `string` | ✓ |  |

### `write_tests`
Generate pytest unit tests for the given function signatures. Happy path + edge + error.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `function_signatures` | `string` | ✓ |  |

---

## Provider — Anthropic

_2 tools_

### `ask_smart`
Smart router — gptoss-120b primary + CF and Cerebras fallback.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_sonnet`
Claude Sonnet 4.6 — balanced quality/speed. The default for code and analysis.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Groq

_9 tools_

### `ask_aya`
Aya 8B (Cohere) — Turkish grammar and style. Runs through the local Ollama.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_deepseek`
DeepSeek Coder v2 16B — bug finder, line-by-line review.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_granite`
IBM Granite 3.1 8B — fact-checking with low hallucination.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_granite_fast`
Granite 2B — micro verifier (<2s).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_groq_fast`
Llama 3.1 8B (Groq) — ultra fast (<0.3s). Short questions, classification.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_kimi`
Kimi K2.5 (CloudFlare) — code generation + strategy. 256K context.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_reasoner`
CF DeepSeek R1 Distill Qwen 32B — edge reasoning.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_rerank`
Cohere Command R+ — rerank-capable chat; cache-aware.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_scout`
Llama 4 Scout 17B (Groq) — instruction following + short tasks.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Cerebras

_1 tool_

### `ask_cerebras`
Cerebras Qwen3 235B — 235B MoE, ~0.3s latency. 1M tokens/day.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Gemini

_12 tools_

### `ask_gemini`
Gemini 2.5 Flash — fast multimodal. Templates, short generation.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_gemini_pro`
Gemini 2.5 Pro — 1M context, deep analysis, multimodal.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_image`
Gemini 2.5 Flash Image — generate an image from a prompt (base64 PNG).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_image_edit`
Edit the supplied base64 image according to the prompt.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |
| `image_base64` | `string` | ✓ |  |

### `gemini_image_pro`
Gemini Image Pro (Nano Banana Pro) — high-quality image generation.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_lite`
Gemini Flash Lite — fast, low-cost single-shot answer.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_search`
Google Search grounded answer + source URLs.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_structured`
JSON schema-guaranteed output. schema_json must be a valid JSON schema string.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |
| `schema_json` | `string` | ✓ |  |

### `gemini_url`
URL context — ask a question about the contents of a URL.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `url` | `string` | ✓ |  |
| `question` | `string` |  |  |

### `gemini_video`
Start a video job with Veo 3.0; returns an operation name (query its status afterwards).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_video_status`
Query the status of a video job (using the operation name returned by gemini_video).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `operation_name` | `string` | ✓ |  |

### `gemini_video_wait`
Wait until a video job finishes (polls every 15s). Simple placeholder.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `operation_name` | `string` | ✓ |  |
| `max_seconds` | `integer` |  |  |

---

## Provider — Cloudflare

_2 tools_

### `ask_cf`
CloudFlare Llama 3.3 70B FP8 Fast — edge latency.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_cf_gptoss`
CloudFlare GPT-OSS 120B — 120B model at the edge, alternative to Groq.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Cohere

_5 tools_

### `ask_cohere_command_r`
Cohere Command R+ 08-2024 — enterprise chat, RAG compatible.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_cohere_embed`
Cohere embed-english-v3.0 — returns a 1024-dim embedding (JSON).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `text` | `string` | ✓ |  |

### `cohere_alert_ack`
Mark an alert as acknowledged.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `alert_id` | `string` | ✓ |  |

### `cohere_alert_status`
Cohere usage + last alert + severity (ok|warn|danger|limit_hit).

### `cohere_alerts_recent`
The last N alert records (newest first).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

---

## Provider — Local

_11 tools_

### `ask_codellama`
CodeLlama 7B — lightweight code and unit test generator.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_gemma2`
Gemma 2 9B — factual, low hallucination.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_llava`
Llava 7B — local image understanding (multimodal).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_longcontext`
Kimi K2.5 (CF) — 256K context long-context alias.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_mlx`
MLX Neural Engine — llama3-8b on Apple Silicon, ~0.3-1s.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_mlx_fast`
MLX Fast — phi3-mini, ultra fast classification <0.5s.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_or_minimax`
OpenRouter MiniMax M2 :free — supports cache_control.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_or_qwen_coder`
OpenRouter Qwen3 Coder 480B :free — SWE-Bench 69.6%.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_phi4`
Phi-4 (local Ollama) — reasoning. Works when OLLAMA_URL is set.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_starcoder`
StarCoder2 3B — FIM code completion + fast lint.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_vllm`
vLLM cluster — self-hosted (requires ABS_VLLM_URL).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Pipeline — Quality

_10 tools_

### `ask_disagree`
Calls 3 providers in parallel + cosine/jaccard similarity + a consensus score.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_analysis`
QUALITY ANALYSIS PIPELINE — 3 perspectives (gptoss + kimi2 + gemini-pro) → synthesis.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_code`
QUALITY CODE PIPELINE — generate (kimi + gpt-oss-20b in parallel) → codellama verify → gpt-oss-120b fix.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_code_human`
QUAL CODE + HUMANIZE — rewrites the qual-code output with the AI-style comments stripped out.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_human`
QUAL + HUMANIZE — rewrites the qual-tr output so that it scores low with AI detectors.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_tr`
QUALITY TURKISH PIPELINE — generate (qwen32b + gemini in parallel) → aya review → kimi2 polish.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_translate`
QUALITY TRANSLATION PIPELINE — translate → back-translate → compare → refine.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race`
RACE — gpt-oss-120b vs kimi vs kimi2 in parallel, first success wins.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race_code`
RACE CODE — CF Kimi K2.5 vs Groq GPT-OSS 120B, first success wins.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race_tr`
RACE TR — Qwen32B vs Gemini 2.5 Flash, first success wins.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## RAG

_6 tools_

### `rag_clear`
Delete the whole collection, or only the chunks of one project.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `project` | `?` |  |  |

### `rag_hybrid`
RAG hybrid retrieval — BM25 + cosine fusion. alpha_semantic 0=BM25, 1=cosine.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `question` | `string` | ✓ |  |
| `project_filter` | `?` |  |  |
| `top_k` | `integer` |  |  |
| `alpha_semantic` | `number` |  |  |

### `rag_index`
Add a file or directory to the RAG index. chunk_strategy: 'semantic' | 'char'.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `path` | `string` | ✓ |  |
| `project` | `string` |  |  |
| `chunk_strategy` | `string` |  |  |

### `rag_query`
Semantic search over the indexed chunks; returns the closest top_k snippets.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `question` | `string` | ✓ |  |
| `project_filter` | `?` |  |  |
| `top_k` | `integer` |  |  |

### `rag_status`
Summary of the RAG collection and its disk usage.

### `symbol_search`
Substring search over the symbol DB — name LIKE %q%, optional kind=function|class|import.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `q` | `string` | ✓ |  |
| `kind` | `?` |  |  |
| `limit` | `integer` |  |  |

---

## Fullstack

_4 tools_

### `fullstack`
Layer-specific code generator — detects the layer automatically and picks the best-suited model.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |
| `layer` | `string` |  |  |

### `fullstack_detect`
Detect the layer from the prompt (frontend/backend/database/devops/testing/docs/architecture).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `fullstack_plan`
Scan + gap analysis + task plan (produced by an LLM).

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `project_dir` | `string` | ✓ |  |

### `fullstack_scan`
Scan a project directory — inventory of files, languages and dependencies.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `project_dir` | `string` | ✓ |  |

---

## Other

_4 tools_

### `ask_cohere_aya`
Cohere Aya Expanse 32B — 101 languages, multilingual tasks including Turkish.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_haiku`
Claude Haiku 4.5 — Anthropic's fast model. Short tasks, classification.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_opus`
Claude Opus 4.7 — Anthropic's most capable model. Deep analysis, critical work.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race_local`
RACE LOCAL — Ollama phi4 vs gemma2. Requires ABS_OLLAMA_URL.

**Parameters:**

| Name | Type | Required | Description |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

