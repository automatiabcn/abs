# FAQ — Sıkça sorulan sorular

15 kısa soru-cevap. Daha derinleştirmek için ilgili sayfaya yönlendirildin.

## Ürün

### 1. ABS nedir?
Self-host AI orchestration. Claude Code'u extend eden 100+ MCP tool, 6 sağlayıcı
cascade (Anthropic + Groq + Cerebras + Gemini + Cloudflare + Cohere), RAG hybrid
ve Türkçe kalite pipeline. Kendi sunucunda çalışır, kullandıkça öder modeli.

### 2. Anthropic TOS uygun mu?
Evet. ABS, Anthropic'in pay-per-use API'sini kullanır (Pro abonelik OAuth değil).
Kendi API anahtarınla bağlanır, prompt'lar Anthropic'e gider, ABS sunucusuna
hiçbir veri gönderilmez.

### 3. Cursor / Cline / Aider varken neden ABS?
ABS bir IDE eklentisi değil — self-host ağ. Bu IDE'lerle paralel kullanılır.
6 sağlayıcı cascade + circuit breaker + token tracking + RAG hybrid + Türkçe
kalite pipeline tek üründe gelir.

## Teknik

### 4. Hangi donanım yeterli?
1 vCPU, 2 GB RAM, 20 GB disk. Hetzner CX22 ($5/ay) veya benzer VPS yeterli.
Production scale (>10 user) için 2 vCPU, 4 GB RAM önerilir.

### 5. Hangi DB?
SQLite + WAL. Toplam 4 tablo: `licenses`, `webhook_events`, `email_queue`,
plus durability stores (workflow_state, judge_log, rag_chroma).
Postgres adapter 022+'a deferred.

### 6. Vault nasıl çalışır?
Mozilla sops + age — Stripe key, Anthropic key, SMTP password disk üzerinde
her zaman şifreli. Boot'ta backend bellekteki settings nesnesine açar. Master
age key ayrı volume (read-only) — backend'in commit edemediği güven sınırı.

### 7. Hangi LLM model'leri destekleniyor?
Anthropic Claude (Opus, Sonnet, Haiku), Groq (GPT-OSS 120B, Qwen3 32B, Kimi K2,
Llama 4 Scout, Llama 3.x), Cerebras Llama, Gemini 2.5 Pro/Flash, Cloudflare
Workers AI (10+ model), Cohere Command R, ve Apple Silicon MLX (Phi-3, Llama3-8B).

## Lisans + Faturalama

### 8. Lisans nasıl çalışır?
JWT RS256, public key sunucuda gömülü, online doğrulama yok. Lisansı kaybedersen
panel'den veya satın alma email'inden tekrar al.

### 9. Demo var mı?
Evet — yeni kurulumda 14 gün otomatik demo aktif. Demo süresince tüm MCP tool'lar
çalışır. Süre dolduğunda `mcp_require_license=true` ise tool'lar engellenir.

### 10. İade politikası?
14 gün koşulsuz. Stripe Customer Portal üzerinden self-service. Refund onaylanır
onaylanmaz lisans `revoked_at` ile pasif olur.

### 11. Yıllık mı, tek seferlik mi?
Self-Host Lifetime $299 — TEK SEFERLİK. Maintenance $49/yıl opsiyonel.
Annual subscription tier 022+'a deferred.

## Veri & Güvenlik

### 12. Verim Anthropic'e gidiyor mu?
Sadece Claude API çağrılarındaki prompt'lar. ABS bir köprü değil — sen sunucunda
istek atıyorsun, Anthropic yanıtlıyor. Automatia BCN sunucularına hiçbir
müşteri verisi gelmez.

### 13. GDPR uyumlu mu?
Evet. Veri sorumlusu Automatia BCN (Barcelona). Kullanıcı verisi ABS'i kullananın
sunucusunda kalır; sadece ödeme verisi Stripe (PCI-DSS) tarafında. AB Madde 15-22
hakları için `privacy@automatiabcn.com`.

### 14. Açık kaynak mı?
Çekirdek (`core/backend`, `core/landing`) Apache 2.0. Premium add-on'lar
(advanced RAG, team panel, gelecek SaaS modu) kapalı kaynak. Self-Host Lifetime
sahibi premium add-on'ları da alır.

## Operasyon

### 15. Güncelleme nasıl gelir?
`docker compose pull && docker compose up -d`. ABS update channel signature
ile imza doğrular (014). Self-Host Lifetime 1 yıl ücretsiz güncelleme.
Sonrası Maintenance $49/yıl.

---

Daha fazla soru? `support@automatiabcn.com` veya GitHub Discussions.
Detaylı bilgi: [Setup Guide](setup-guide.md), [API Reference](api-reference.md).
