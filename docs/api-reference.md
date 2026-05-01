# API Reference — MCP Tools
Bu sayfa otomatik üretilir (`python scripts/gen_api_reference.py`). Manuel düzenleme yapma.
Toplam **104 tool** — kategorilere göre alfabetik sıralı.
Her MCP tool, Claude Code'da `claude mcp add abs <url>` sonrası `mcp__abs__<tool>` olarak veya orchestrator alias'larla (`ask "..." gptoss` vb.) çağrılabilir.

## Sistem & Sağlık

_38 tool_

### `apply_patch`
Unified diff'i uygula (atomic + backup). Rollback başarısız olursa reason döner.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `file_path` | `string` | ✓ |  |
| `unified_diff` | `string` | ✓ |  |
| `backup` | `boolean` |  |  |

### `auto_verify_code`
PC GPU paralel kod doğrulama — granite-2b security + codellama test + deepseek lint.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `code` | `string` | ✓ |  |

### `auto_verify_turkish`
Türkçe metin kalite kontrolü — aya-8b ile gramer/stil.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `text` | `string` | ✓ |  |

### `billing_status`
017 — ABS billing dashboard: Stripe + DB lisans + son 10 webhook event.

### `breaker_status`
Cascade circuit breaker state'leri (open/half_open/closed).

### `cache_stats`
Semantic cache istatistikleri (hit/miss/entries/hit_rate).

### `code_fingerprint`
Kod için fingerprint: SHA-256 + satır/fonksiyon sayısı + basit metrikler.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `code` | `string` | ✓ |  |

### `code_review`
Code review — tier auto (quick <50 sat, standard 50-200, exhaustive 200+).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `code` | `string` | ✓ |  |
| `tier` | `string` |  |  |

### `daily_cost`
tracker × provider_configs pricing → bugunku tahmini maliyet.

### `demo_status`
Demo countdown durum (started/expired/days_remaining).

### `email_queue_status`
ABS onboarding email kuyruk dashboard.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

### `freeze`
Freeze mode'u aç: sadece verilen dizin içinde Write/Edit'e izin ver.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `project_dir` | `string` |  |  |

### `health_status`
Tum provider'larin real-time ping durumu.

### `humanize_score`
Input metninin 'AI-written' heuristik skoru (0=insani, 1=AI). JSON döner.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `text` | `string` | ✓ |  |

### `investigate`
Investigate mode — kök neden araştırma modu aç. Hook'lar uyarı verir.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `topic` | `string` |  |  |

### `judge_outcome`
Bir judgment'a outcome işaretle (accept|reject).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `judgment_id` | `string` | ✓ |  |
| `outcome` | `string` |  |  |

### `judge_patch`
SENIOR JUDGE — diff AST + LLM birleşik skoru. %60 fingerprint + %40 LLM.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `unified_diff` | `string` | ✓ |  |
| `file_path` | `string` |  |  |

### `judge_persona_predict`
ML model ile bu skorlarin accept olasiligini tahmin et.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `ast_score` | `number` | ✓ |  |
| `llm_score` | `number` | ✓ |  |
| `persona_drift` | `number` | ✓ |  |

### `judge_persona_reset`
Persona'yı DEFAULT_PERSONA'ya geri al (history dosyası korunur).

### `judge_persona_status`
Mevcut persona threshold'ları + son training meta + history boyutu.

### `judge_persona_train`
judge_log outcome'larından persona dynamic adjust. min_samples altında 'insufficient_data'.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `min_samples` | `integer` |  |  |

### `judge_recent`
Son N judgment kaydı (id, ts, file, ast/llm/combined, outcome).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

### `judge_stats`
Son N günün judgment ortalamaları + drift_signal + outcome_counts + top_files.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `window_days` | `integer` |  |  |

### `learnings_log`
Manuel learning ekle. category: bugfix|delegation|arch|security|perf|ux.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `category` | `string` | ✓ |  |
| `lesson` | `string` | ✓ |  |
| `project` | `?` |  |  |

### `learnings_recent`
Son N learning kaydi + kategorik istatistikler.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

### `license_status`
ABS lisans + demo durum snapshot — JSON doner.

### `model_health`
Basit model health skoru — breaker state üzerinden.

### `preview_patch`
Unified diff'i dry-run uygula, success + reason döndür.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `file_path` | `string` | ✓ |  |
| `unified_diff` | `string` | ✓ |  |

### `quota_status`
Provider kota durumu (breaker state snapshot).

### `score_patch_quality`
Patch'e 0-10 minimalism + hunk konsantrasyon skoru ver.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `unified_diff` | `string` | ✓ |  |

### `setup_status`
Müşteri kurulum wizard'ının mevcut durumu — JSON döner.

### `system_status`
ABS sistem durumu — lisans, provider breaker state, cache, tool kullanımı.

### `update_check`
Remote release manifest → version compare → state JSON.

### `vault_status`
Vault snapshot — configured key listesi + audit son 5 olay. Cleartext YOK.

### `workflow_resume`
Bir workflow'un son başarılı adımdan devam state'ini döndür.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `trace_id` | `string` | ✓ |  |

### `workflow_status`
Workflow durability snapshot — toplam, by_status, son 5 + db_size_kb.

### `write_docs`
Modül / fonksiyon için Türkçe API dokümantasyonu (markdown).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `module_info` | `string` | ✓ |  |

### `write_tests`
Fonksiyon imzaları için pytest unit test üret. Happy + edge + error.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `function_signatures` | `string` | ✓ |  |

---

## Provider — Anthropic

_2 tool_

### `ask_smart`
Akıllı router — gptoss-120b primary + CF + Cerebras fallback.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_sonnet`
Claude Sonnet 4.6 — dengeli kalite/hız. Kod + analiz için default.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Groq

_9 tool_

### `ask_aya`
Aya 8B (Cohere) — Türkçe gramer + stil. Yerel Ollama üzerinden.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_deepseek`
DeepSeek Coder v2 16B — bug finder, satır bazlı review.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_granite`
IBM Granite 3.1 8B — düşük hallucination fact-check.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_granite_fast`
Granite 2B — mikro doğrulayıcı (<2s).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_groq_fast`
Llama 3.1 8B (Groq) — ultra hızlı (<0.3s). Kısa sorular, sınıflandırma.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_kimi`
Kimi K2.5 (CloudFlare) — kod üretimi + strateji. 256K context.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_reasoner`
CF DeepSeek R1 Distill Qwen 32B — edge reasoning.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_rerank`
Cohere Command R+ — rerank-capable chat; cache-aware.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_scout`
Llama 4 Scout 17B (Groq) — talimat takibi + kısa görev.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Cerebras

_1 tool_

### `ask_cerebras`
Cerebras Qwen3 235B — 235B MoE, ~0.3s latency. 1M tok/gün.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Gemini

_12 tool_

### `ask_gemini`
Gemini 2.5 Flash — hızlı multimodal. Template, kısa üretim.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_gemini_pro`
Gemini 2.5 Pro — 1M context, derin analiz, multimodal.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_image`
Gemini 2.5 Flash Image — prompt'tan görsel üret (base64 PNG).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_image_edit`
Verilen base64 görseli prompt'a göre düzenle.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |
| `image_base64` | `string` | ✓ |  |

### `gemini_image_pro`
Gemini Image Pro (Nano Banana Pro) — yüksek kalite görsel.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_lite`
Gemini Flash Lite — hızlı ve düşük maliyetli tek-shot yanıt.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_search`
Google Search grounded yanıt + kaynak URL'leri.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_structured`
JSON schema-guaranteed output. schema_json geçerli JSON schema string'i.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |
| `schema_json` | `string` | ✓ |  |

### `gemini_url`
URL context — bir URL'nin içeriği hakkında soru sor.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `url` | `string` | ✓ |  |
| `question` | `string` |  |  |

### `gemini_video`
Veo 3.0 ile video jobu başlat; operation name döner (sonra status).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `gemini_video_status`
Video job durumu sorgula (gemini_video'dan dönen operation name ile).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `operation_name` | `string` | ✓ |  |

### `gemini_video_wait`
Video job bitene kadar bekle (polling her 15s). Basit placeholder.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `operation_name` | `string` | ✓ |  |
| `max_seconds` | `integer` |  |  |

---

## Provider — Cloudflare

_2 tool_

### `ask_cf`
CloudFlare Llama 3.3 70B FP8 Fast — edge latency.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_cf_gptoss`
CloudFlare GPT-OSS 120B — edge 120B model, Groq alternatifi.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Provider — Cohere

_5 tool_

### `ask_cohere_command_r`
Cohere Command R+ 08-2024 — enterprise chat, RAG uyumlu.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_cohere_embed`
Cohere embed-english-v3.0 — 1024-dim embedding döndürür (JSON).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `text` | `string` | ✓ |  |

### `cohere_alert_ack`
Bir alert'i acknowledge işaretle.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `alert_id` | `string` | ✓ |  |

### `cohere_alert_status`
Cohere kullanım + son alert + severity (ok|warn|danger|limit_hit).

### `cohere_alerts_recent`
Son N alert kaydı (en yeni önce).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `limit` | `integer` |  |  |

---

## Provider — Lokal

_11 tool_

### `ask_codellama`
CodeLlama 7B — hafif kod + unit test üretici.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_gemma2`
Gemma 2 9B — factual, düşük hallucination.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_llava`
Llava 7B — yerel görsel anlama (multimodal).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_longcontext`
Kimi K2.5 (CF) — 256K context long-context alias.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_mlx`
MLX Neural Engine — Apple Silicon (M4) llama3-8b ~0.3-1s.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_mlx_fast`
MLX Fast — phi3-mini ultra hızlı sınıflandırma <0.5s.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_or_minimax`
OpenRouter MiniMax M2 :free — cache_control destekli.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_or_qwen_coder`
OpenRouter Qwen3 Coder 480B :free — SWE-Bench 69.6%.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_phi4`
Phi-4 (yerel Ollama) — reasoning. OLLAMA_URL tanımlıysa çalışır.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_starcoder`
StarCoder2 3B — FIM kod tamamlama + hızlı lint.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_vllm`
vLLM cluster — self-host (ABS_VLLM_URL gerekli).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## Pipeline — Kalite

_10 tool_

### `ask_disagree`
3 provider paralel çağrı + cosine/jaccard similarity + consensus skoru.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_analysis`
KALİTE ANALİZ PIPELINE — 3 perspektif (gptoss + kimi2 + gemini-pro) → sentez.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_code`
KALİTE KOD PIPELINE — Üret(kimi+gpt-oss-20b paralel) → codellama verify → gpt-oss-120b fix.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_code_human`
QUAL CODE + HUMANIZE — qual-code çıktısını AI-yorumları kaldırarak yeniden yazar.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_human`
QUAL + HUMANIZE — qual-tr çıktısını AI-detector'dan düşük puan alacak şekilde dönüştürür.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_tr`
KALİTE TÜRKÇE PIPELINE — Üret(qwen32b+gemini paralel) → aya review → kimi2 polish.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `qual_translate`
KALİTE ÇEVİRİ PIPELINE — çevir → geri-çevir → karşılaştır → refine.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race`
RACE — gpt-oss-120b vs kimi vs kimi2 paralel, ilk başarılı kazanır.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race_code`
RACE CODE — CF Kimi K2.5 vs Groq GPT-OSS 120B, ilk başarılı.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race_tr`
RACE TR — Qwen32B vs Gemini 2.5 Flash, ilk başarılı.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

## RAG

_6 tool_

### `rag_clear`
Tüm koleksiyonu veya yalnızca bir project'in chunk'larını sil.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `project` | `?` |  |  |

### `rag_hybrid`
RAG hybrid retrieval — BM25 + cosine fusion. alpha_semantic 0=BM25, 1=cosine.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `question` | `string` | ✓ |  |
| `project_filter` | `?` |  |  |
| `top_k` | `integer` |  |  |
| `alpha_semantic` | `number` |  |  |

### `rag_index`
Bir dosya/dizini RAG index'ine ekle. chunk_strategy: 'semantic' | 'char'.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `path` | `string` | ✓ |  |
| `project` | `string` |  |  |
| `chunk_strategy` | `string` |  |  |

### `rag_query`
Index'lenmiş chunk'larda anlam bazlı arama; en yakın top_k snippet döner.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `question` | `string` | ✓ |  |
| `project_filter` | `?` |  |  |
| `top_k` | `integer` |  |  |

### `rag_status`
RAG koleksiyon ve disk kullanım özeti.

### `symbol_search`
Symbol DB substring search — name LIKE %q%, opsiyonel kind=function|class|import.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `q` | `string` | ✓ |  |
| `kind` | `?` |  |  |
| `limit` | `integer` |  |  |

---

## Fullstack

_4 tool_

### `fullstack`
Katman-özel kod üretici — auto katman tespit + en uygun model.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |
| `layer` | `string` |  |  |

### `fullstack_detect`
Prompt'tan katman tespit et (frontend/backend/database/devops/testing/docs/architecture).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `fullstack_plan`
Scan + gap analizi + görev planı (LLM ile).

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `project_dir` | `string` | ✓ |  |

### `fullstack_scan`
Proje dizinini tara — dosya/lang/deps envanteri.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `project_dir` | `string` | ✓ |  |

---

## Diğer

_4 tool_

### `ask_cohere_aya`
Cohere Aya Expanse 32B — 101 dil, çok-dilli görev + Türkçe.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_haiku`
Claude Haiku 4.5 — Anthropic'in hızlı modeli. Kısa görev, sınıflandırma.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `ask_opus`
Claude Opus 4.7 — Anthropic'in en güçlü modeli. Derin analiz, kritik görev.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

### `race_local`
RACE LOCAL — Ollama phi4 vs gemma2. ABS_OLLAMA_URL gerekli.

**Parametreler:**

| İsim | Tip | Zorunlu | Açıklama |
|---|---|:-:|---|
| `prompt` | `string` | ✓ |  |

---

