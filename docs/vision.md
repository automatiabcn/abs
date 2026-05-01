# Vision — Tek Sayfada

## Ne yapıyoruz

**$20 Claude Pro planını $200 Max plan verimine dönüştüren self-hosted orchestration katmanı.**

## Kim için

**10-50 kişilik tech firmalar.** CTO ya da VP Eng karar verir; ekipteki her geliştirici kendi $20/ay Claude Pro hesabıyla terminal'den bağlanır.

## Nasıl

Müşteri:
1. Bir Linux sunucu kiralar (Hetzner, DO, AWS — $15-100/ay)
2. ABS'yi Docker Compose ile kurar (~15 dakika)
3. Web setup wizard ile 6 API key girer (hepsi free tier: Anthropic + Groq + Cerebras + CloudFlare + Gemini + Cohere)
4. Ekibini davet eder (SSO veya email)
5. Her geliştirici `claude mcp add abs https://abs.company.com/mcp` ile bağlanır

Arka planda ABS:
- Claude prompt'unu inceler, **delegasyon uygun mu** karar verir
- Uygunsa **free provider havuzuna** yönlendirir (Groq GPT-OSS 120B, Cerebras Qwen 235B, CF Kimi K2.5, Gemini Flash)
- Çıktı kalite pipeline'larından (qual-code, qual-tr, qual-analysis) geçer
- Senior Judge skor verir, düşükse re-roll
- RAG (proje sembolleri) + workflow durability + cache hit catcher
- Panel'de audit log + budget tracker + quota alerts

Sonuç: Claude token **minimum** tüketilir (orkestrasyon için), iş yükü **free provider'larda**, **kalite yüksek**.

## Değer Önermesi (CFO için)

10 kişilik ekip:
- **ABS olmadan:** Her geliştirici Max 5x ($100/ay) → **$1000/ay**
- **ABS ile:** Her geliştirici $20 Pro + ABS Business ($29/user/ay) → **$490/ay + sunucu $30/ay = $520/ay**
- **Tasarruf:** $480/ay × 12 = **$5.760/yıl**

50 kişilik ekip:
- ABS olmadan Max 20x: $10.000/ay
- ABS ile: $20 Pro + Business: $2.450/ay + sunucu $50/ay = $2.500/ay
- Tasarruf: $7.500/ay × 12 = **$90.000/yıl**

## Bizim Farkımız (rakipler arasında)

| Rakip | Ne yapar | ABS farkı |
|---|---|---|
| LiteLLM | Provider proxy | ABS hook + RAG + judge + panel + TR pipeline |
| Aider | Claude Code dışı terminal tool | ABS Claude Code'u **genişletir**, alternatif değil |
| Cline / Cursor | IDE-bound | ABS terminal-native + herhangi editör |
| Claude Code (vanilla) | MCP + hook altyapısı var | ABS üzerine 75 tool + 13 pipeline + panel inşa eder |
| Vercel AI Gateway | Production app proxy | ABS dev workflow için |

**Net:** Kimse "Claude Code'un $20 planını production ekibe genişleten bir orchestration platformu" satmıyor. Bu boş niş.

## Sınır (dürüst)

- **Solo operatör** (Enes). 20-30 müşteri tavan, sonra ekip lazım.
- **Anthropic TOS** cevapsız — Claude Pro plan'ı orchestrate etmek resmi onay gerektirebilir.
- **Müşteri kodu Claude prompt'una gider** → Anthropic'e ulaşır (data residency transparent olmalı).
- **Free tier'lar sonsuz değil** — Cohere 1000/ay, Gemini 1500/gün. Aşım = paid fallback veya hard cap.
- **macOS → Linux port** — MLX, LaunchAgent, Tailscale gibi bileşenler Linux alternatifine dönüşecek.

## Başarı Ölçüsü

**MVP sonrası 6 ay:**
- 10-20 Business müşteri ($3-10K/ay ARR)
- 2-3 Enterprise müşteri ($2-5K/ay ARR)
- Toplam ~$10-25K/ay ARR (solo operatörün tavanı)

Bu noktadan sonra ekip genişletme kararı.
