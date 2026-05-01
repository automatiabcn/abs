# LLM Sağlayıcı Ücretsiz Katman Limitleri (Nisan 2026)

Bu belge, Automatia ABS'nin kullandığı LLM sağlayıcılarının ücretsiz katman limitlerini Nisan 2026 itibarıyla kaydeder. ABS Central Watchdog bu sayıları aylık doğrular.

## Özet Tablo

| Sağlayıcı | Free Tier Limit | Kredi Kartı | Notlar |
|---|---|---|---|
| **Anthropic** | Pay-as-you-go (minimum $0) | ✅ Gerekli | Sonnet 4.6: $3/1M input + $15/1M output |
| **Groq** | Llama 3.1 8B: 14.400 req/gün, 500K token/gün; Llama 3.3 70B: 1.000 req/gün, 100K token/gün; 30 RPM | ❌ | Çoklu model desteği |
| **Cerebras** | 1 milyon token/gün, 30 RPM | ❌ | Qwen3 235B, GPT-OSS 120B, Qwen-3-Coder-480B dahil |
| **CloudFlare Workers AI** | 10.000 Neurons/gün (Workers free plan) | ❌ | Llama 3.2, Mistral 7B, Kimi K2.5 |
| **Gemini (AI Studio)** | Flash/Flash-Lite 500 RPD; Pro 100 RPD | ❌ | 200K context (2.5 Pro), 2M context (3 Pro Preview) |
| **Cohere** | 1.000 API call/**AY** (tüm endpoint) | ❌ | Rerank + Command R + Embed + Aya |
| **Mistral** | 1 MİLYAR token/ay, 2 RPM | ❌ (telefon) | Tüm modeller, Experiment tier |
| **OpenRouter** | Free modeller: 20 RPM / 50 req/gün/model | ❌ | GPT-OSS 120B, Llama 3.3 70B, DeepSeek R1, Qwen3 Coder 480B |

## Kullanım Senaryoları

### 1 geliştirici (50-100 prompt/gün)
- Free cascade yeterli
- Anthropic API kullanımı: ~$0.50-5/ay tahmini
- **Toplam aylık maliyet: $0.50-5** (Pro subscription gerek yok)

### 5 kişilik takım (250-500 prompt/gün)
- Free cascade hâlâ yeterli
- Anthropic: ~$5-25/ay
- Cohere 1000/ay limiti dikkat (rerank yoğun kullanıldığında)

### 10 kişilik ekip (500-1000 prompt/gün)
- Cascade içinde Cohere aylık limit'i ilk darboğaz
- Fallback: rerank yerine qual-analysis ensemble
- Anthropic: ~$10-50/ay
- Mistral 1B token/ay müthiş buffer

## Anthropic API (pay-as-you-go)

- **Minimum spend:** $0 (pay-per-use, sabit ücret yok)
- **Sonnet 4.6:** $3/1M input, $15/1M output
- **Haiku 4.5:** ~$0.80/1M input, $4/1M output (ekonomik kullanım için önerilen)

**Örnek hesap (Haiku, 10 kişi, cascade ile Anthropic'e giden ~%15):**
- 10.000 prompt/ay → ~1.500 Anthropic çağrısı
- 1.500 × (2K input + 500 output) = 3M input + 750K output
- Haiku: $0.80 × 3 + $4 × 0.75 = **$5.40/ay**

## Risk ve Sınır Uyarısı

⚠ **"Şu an ücretsiz" ≠ "ömür boyu ücretsiz garantisi".**

Sağlayıcılar tek taraflı olarak free tier kaldırabilir, sınır düşürebilir, kredi kartı zorunluluğu ekleyebilir. Geçmiş örnekler:
- DALL-E (OpenAI): önce free, sonra paid-only
- Affinity: Canva acquisition sonrası free oldu (artı)
- Bazı Gemini modelleri free'den paid'e geçti

## ABS Central Watchdog Koruma

ABS'nin koruması için çok katmanlı:

1. **Günlük scan**: Bizim tarafta `abs.automatiabcn.com/watchdog/` sağlayıcı pricing sayfaları + changelog RSS + status JSON
2. **Cascade fallback**: Bir sağlayıcı bozulursa sistemde otomatik diğerine geçer
3. **Update channel**: Sağlayıcı değişince yeni `provider_configs/*.yaml` release'i gelir, müşteri `docker-compose pull` ile alır
4. **Panel uyarısı**: Müşteri panel'inde banner "Cohere free tier kaldırıldı, rerank devre dışı" gibi şeffaf bildirim

Detay: `docs/operations.md` — Central Watchdog + Update Channel mimarisi.

## Resmi URL Referansları (doğrulama için)

- Groq: console.groq.com/settings/limits
- Cerebras: cerebras.ai/inference-pricing
- CloudFlare: developers.cloudflare.com/workers-ai/platform/pricing
- Gemini: ai.google.dev/gemini-api/docs/rate-limits
- Cohere: cohere.com/pricing
- Mistral: mistral.ai/pricing
- OpenRouter: openrouter.ai/docs/models (free modeller)
- Anthropic: anthropic.com/pricing

---

**Son doğrulama tarihi:** 2026-04-23 (Gemini Search ile)
**Sonraki plan kontrol:** Apr 30 + Mayıs başı (Central Watchdog aktifleşince otomatik)
