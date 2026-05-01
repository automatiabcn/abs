# ABS Demo — 5-7 Minute Loom Script

**Last updated:** 2026-04-27  
**Format:** Timestamped with camera & voice directions  
**Target audience:** CTOs, DevOps engineers, self-hosted stack evaluators  
**Total runtime:** ~5-7 minutes (~600 words bilingual)

---

## PART 1: ENGLISH SCRIPT (~400 words)

### 0:00–0:30 HOOK & VALUE PROP

**[CAMERA: Face-cam, presenter at desk]**  
**[VOICE: Warm, confident, conversational]**

> "Hey! I'm [Your Name], founder of ABS. If you're running infrastructure and you're tired of paying $1,000+ per year for enterprise AI stacks that lock you in, this one's for you.
>
> **ABS puts 119 MCP tools and 6-provider cascade on your own server for $299—lifetime license.** No subscriptions. No vendor lock-in. Enterprise-grade AI orchestration at indie pricing.
>
> Let me show you what I mean."

**[Transition cue: Screen fades to abs.automatiabcn.com pricing page]**

---

### 0:30–1:30 LANDING PAGE & PRICING

**[CAMERA: Screen share, full browser view]**  
**[VOICE: Calm, matter-of-fact, data-focused]**

*Scroll to pricing section slowly. Position: https://abs.automatiabcn.com — pricing table center-right.*

> "Here's the reality: a typical enterprise AI stack—vector DBs, multi-model orchestration, compliance tooling, audit logging—runs **$800 to $2,000 annually.** Plus implementation time. Plus ongoing support contracts.
>
> **ABS: $299. One-time.**
>
> That includes everything. Groq, Gemini, Cohere, Cloudflare, Cerebras, OpenRouter. All six providers. All 119 MCP tools. Compliance dashboards. On-premise. Your data, your rules."

*Pause 2–3 seconds on pricing comparison.*

**[Transition cue: "Let me show you how fast this actually sets up."]**

---

### 1:30–3:00 SETUP WIZARD (Sped 3×)

**[CAMERA: Screen share — split view: terminal left, UI right]**  
**[VOICE: Efficient, matter-of-fact, encouraging]**

*Show sequence at 3× speed:*

1. **`docker compose up`** — Docker pulls, builds, starts containers (~30 sec in real-time, 10 sec sped)
2. **License modal** — Enter license key, system validates (~5 sec real, 2 sec sped)
3. **Provider config** — Dropdown menu: select Groq, Gemini, Cohere; paste API keys; save (~15 sec real, 5 sec sped)

> "Docker compose. License key. API keys. Done. **Three minutes. No rabbit holes.**
>
> And it's live right now."

**[Transition cue: "Let's run some actual MCP tools. Real data, no scripts."]**

---

### 3:00–5:00 LIVE MCP TOOL DEMO

**[CAMERA: Screen share — admin dashboard, full viewport]**  
**[VOICE: Excited but precise, emphasize real-time results]**

*Run actual commands; show live output:*

**Command 1: `system_status`**
> "This shows you what's online. Model availability, token consumption, uptime. All real."

*Display: Groq ✓ online, Gemini ✓ online, Cohere ✓ online, 42,340 tokens used this week, 99.8% uptime*

**Command 2: `ask_groq_fast "summarize this legal document"`**
> "Paste in a 10-paragraph PDF excerpt. Watch what happens in 2 seconds."

*Paste dummy legal text → Output: Clean, accurate 3-sentence summary. Timestamp: 2.1s.*

> "Two seconds. Legal summarization. Zero hallucination."

**Command 3: `news_digest`**
> "Live AI news fetch. No cache, no delays."

*Display: 5 trending stories, fetched 2 minutes ago, from HackerNews/ArXiv.*

**Command 4: `compliance_status`**
> "GDPR/SOC2 compliance gap analysis. Real-time."

*Display: GDPR ✓ 92% aligned, SOC2 ⧐ 67% aligned (gaps listed), audit log count: 2,847 entries*

> "This is real infrastructure. Not a demo. Not a mock. **Live production system.**"

**[Transition cue: "Now, the thing that matters most: your data stays yours."]**

---

### 5:00–6:30 PRIVACY, ADMIN DASHBOARD & COMPLIANCE

**[CAMERA: Screen share — sequential page transitions]**  
**[VOICE: Reassuring, professional, emphatic on privacy]**

**Page 1: `/privacy` — Multi-language**
> "Privacy policy. In three languages, because your users might be anywhere."

*Quick cycle: EN (3 sec) → TR (3 sec) → ES (3 sec). Show GDPR/CCPA compliance statements.*

**Page 2: Admin Dashboard**
> "User management, API usage graphs, cost tracking by provider. Complete visibility."

*Show: User table (name, role, last login), usage chart (Groq 45%, Gemini 30%, Cohere 25%), cost breakdown ($12.50 this month).*

**Page 3: Compliance Status Widget**
> "Gap analysis, audit logs, data residency confirmation."

*Show: Audit log (scrollable), latest 5 entries (e.g., "2026-04-27 14:32 API key rotated", "2026-04-27 09:15 User invited").*

> "Your data lives on your server. Full audit trail. No mystery calls home. **Fully auditable.**"

**[Transition cue: "Ready to try it? Here's how."]**

---

### 6:30–7:00 CLOSING CTA

**[CAMERA: Split screen — face-cam (left 40%), `/beta` page (right 60%)]**  
**[VOICE: Energetic, accessible, warm]**

> "Get ABS beta access today. **30 days completely free.** No credit card. No strings.
>
> Head to **`abs.automatiabcn.com/beta`** and sign up. We'll provision a server for you in 5 minutes.
>
> Questions? Reply to your welcome email. I read every one.
>
> Thanks for watching!"

*[Presenter gives brief wave/smile, fade to ABS logo for 2 seconds, end.]*

---

## PRODUCTION NOTES

**Camera angles:**
- 0:00–0:30: Face-cam, desk setup, natural lighting
- 0:30–6:30: Screen share (full browser), cursor highlights on key UI elements
- 6:30–7:00: Picture-in-picture (face + screen)

**Voice pacing:**
- Spoken pace: ~130 words per minute
- Pause 2–3 seconds after price numbers, demo results
- Pause 1–2 seconds between major sections (transition silence builds anticipation)

**Editing tips:**
- Speed up docker compose output 3× (use ffmpeg or Loom native speed control)
- Highlight key metrics with yellow/orange box overlays during demo section
- Use slide transitions between sections (fade, 0.5s)
- Add subtle background music (royalty-free, low volume, ~-20dB)

**Script callouts:**
- Replace `[Your Name]` with presenter name
- All URLs are placeholder; verify production URLs before recording
- Command outputs should be genuine live runs (record 2–3 takes to ensure reliability)

---

## PART 2: TR YÖNETİCİ ÖZETI (~200 words)

**Format:** Ekran kaydı script (voiceover only, no face-cam)  
**Runtime:** ~3 minutes (admin walkthrough)  
**Audience:** Türkçe konuşan CTO/DevOps yöneticileri

### YAPI

**Bölüm 1: Sorun (0:00–0:40)**

> "Kuruluş veri merkezinde AI orchestration kuruyorsunuz. Standart enterprise stack sorunları:
>
> - **Maliyet:** Groq + Gemini + Cohere entegrasyonu = 1,200$ +/yıl
> - **Vendor lock-in:** Bir sağlayıcıya bağlanırsanız, portabilite sıkıntı
> - **Gizlilik:** Cloud-only çözümlerde data residency kontrol yok
> - **Uygulama:** Setup haftalarca sürer, team training gerekir"

**Bölüm 2: ABS Çözümü (0:40–1:30)**

> "**ABS: Single, self-hosted orchestrator. 299$ one-time.**
>
> Ne aldığınız:
> - 119 MCP aracı (sistem kontrol, analiz, data fetch, compliance)
> - 6 provider cascade (Groq, Gemini, Cohere, Cloudflare, Cerebras, OpenRouter)
> - On-premise deployment (veri size şirkette kalır)
> - Docker Compose kurulum (3 dakika, sıradan DevOps bilgisi yeterli)
> - Tam audit log + GDPR/SOC2 dashboard"

**Bölüm 3: Canlı Demo & Kapanış (1:30–3:00)**

*Screen share: Admin dashboard göster*

> "System status → Model kullanım → Token tracking → Compliance gaps.
>
> **Setup 3 dakika. Canlı sistem. Gerçek data.**
>
> 30 gün deneme, kredi kartı yok. `/beta`'da başlayın. Sorular? Email atın, 24 saat içinde cevap."

---

## ÖZET & ISTATISTIKLER

| Metrik | Sayı |
|--------|------|
| **English section word count** | ~400 |
| **Turkish section word count** | ~200 |
| **Total bilingual script** | ~600 |
| **Estimated spoken runtime** | 5–7 minutes |
| **Script format** | Markdown, timestamped |
| **Camera transitions** | 5 (face → screen → split) |
| **Live demo commands** | 4 |
| **Languages featured** | EN, TR, ES (in privacy demo) |
| **Call-to-action URLs** | 2 (abs.automatiabcn.com, /beta) |

---

**Production ready:** Yes  
**Last reviewed:** 2026-04-27  
**Status:** Ready for Loom recording
