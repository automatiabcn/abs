# First Customer Playbook

Hedef: ABS'nin **ilk 3 ücretli müşterisi** + **5 beta lisansı**. Solo operatör
için 12 haftalık taktik playbook (sprint formatı).

---

## Faz 1 — Beta Lisansları (Hafta 1-2)

### 1.1 Beta lisans manuel üretme

Üretim sunucusunda:
```bash
docker compose exec abs-backend python -c "
from app.licensing import generate_license
token = generate_license(
    customer_id='beta:friend-1',
    tier='self-host',
    seat_count=1,
    duration_days=180,  # 6 ay beta
)
print(token)
"
```

Sonra DB'ye License row ekle:
```python
from datetime import datetime, timezone, timedelta
from sqlmodel import Session
from app.db.session import get_engine
from app.db.models import License
from app.licensing import verify_license
payload = verify_license(token)
with Session(get_engine()) as db:
    db.add(License(
        jti=payload["jti"],
        customer_email="friend@example.com",
        customer_id_stripe="",  # beta — Stripe customer yok
        tier="self-host", seat_count=1,
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    ))
    db.commit()
```

Email gönder:
```python
from app.email.sender import send_license_email
send_license_email(to="friend@example.com", license_key=token, refund_url="")
```

### 1.2 Beta hedef listesi (5 kişi)

- 2× Türkiye CTO (LinkedIn network — kişisel ilişki)
- 2× ES/EU indie hacker (Twitter dev community)
- 1× kişisel kullanım — kurucu dogfood (doğrulama, en kritik beta)

### 1.3 Beta feedback toplama

- Slack channel veya Discord (özel #abs-beta).
- Haftalık 30dk video call (Zoom/Meet, kayıt al).
- Bug report → GitHub issues `beta` label.
- Onboarding süresi ölç: `setup_state.json` `started_at`/`completed_at` farkı,
  hedef <10dk.

---

## Faz 2 — Landing + Outreach (Hafta 3-4)

### 2.1 Landing page eksikleri (017 sonrası 018'e deferred)

- Hero CTA "Start Free Trial" → demo countdown.
- Pricing table (3 SKU, /year vs /one-time vurgu).
- Social proof (beta tester quote/screenshot).
- FAQ — "Anthropic TOS uygun mu?", "Vault nasıl çalışır?", "Veri Anthropic'e
  gider mi?", "Refund nasıl alırım?".
- Demo screencast (Loom, 3 dk).

### 2.2 Outreach Scripts

**LinkedIn (CTO 10-50 kişilik firma) — ilk mesaj:**
```
Merhaba [İsim],

Automatia ABS'in kurucusuyum — Claude Code'u extend eden self-host bir
orchestrator geliştirdik. 75+ MCP tool, 6 provider cascade (Groq/Cerebras/
Gemini/CF/Cohere/Anthropic), RAG hybrid + Türkçe quality pipeline.

Ekibinizde 10+ developer Claude kullanıyorsa, $20 plan + ABS = $200 Max plan
kalitesi elde ediyorsunuz. ROI: 10 kişilik ekip → ~$1300/ay tasarruf.

Demo (15 dk) için müsait misiniz?

—Automatia BCN
```

**Twitter/X (build-in-public):**
```
🚀 ABS v1.0 launch:
• Self-host AI orchestration for Claude Code
• 75+ MCP tools + 6 providers (Groq/Cerebras/Gemini/CF/Cohere)
• 14-day free demo, $299 self-host
• Open core (Apache 2.0 backend)

Demo: abs.automatiabcn.com/demo
```

**HN Show:**
```
Title: Show HN: Automatia ABS — self-host orchestration for Claude Code ($299)

Body:
I built ABS over 6 months to extend my $20 Claude Pro plan with multi-provider
routing (Groq/Cerebras/Gemini), RAG, and Turkish quality pipelines. After
dogfooding daily I decided to release it.

Tech: FastAPI + SQLite + sops/age vault + Docker. 75+ MCP tools, 100+ HTTP
endpoints, idempotent Stripe webhooks. Privacy: customer code never leaves
their server (only Claude prompts go to Anthropic — transparent in FAQ).

Demo: abs.automatiabcn.com
Repo: github.com/automatiabcn/abs (Apache 2.0 core)

Happy to answer questions.
```

### 2.3 Waitlist email sequence

**Email 1 — Welcome (signup +0h):**
- Konu: "Welcome to ABS waitlist — what you get"
- İçerik: ABS nedir, ne çözer, beta lisans erken erişim.
- CTA: Twitter follow + roadmap link.

**Email 2 — Demo screencast (signup +3 gün):**
- Konu: "ABS in action — 3-min demo"
- 3 dakikalık Loom: setup wizard + Claude Code tool çağrı + panel.
- CTA: "Reply with your use case for a custom demo".

**Email 3 — Launch (signup +7 gün, launch günü):**
- Konu: "ABS is live — first 50 customers get 50% off"
- Indirim kodu (`FIRST50` — Stripe coupon, manuel oluştur).
- CTA: "Start free 14-day trial" → demo link.

---

## Faz 3 — Launch Day (Hafta 5)

### 3.1 Launch checklist

- [ ] Landing page premium SVG illustrations (017 — 018'e deferred).
- [ ] Stripe live products + webhook live (017 §1).
- [ ] HN Show post taslağı hazır (1-2 saat içinde post).
- [ ] Twitter thread (8 tweet, dogfooding süreci).
- [ ] Indie Hacker post.
- [ ] r/selfhosted post (ALLOWED, dikkatli wording — sub kuralları oku).
- [ ] r/ClaudeAI post (alternatif: r/ChatGPTCoding, r/LocalLLaMA).
- [ ] ABS webhook 17/24 monitor görünür (`billing_status` MCP tool görseli).

### 3.2 Launch günü zaman çizelgesi (UTC)

- 12:00 — HN Show post (peak EU/US overlap).
- 12:15 — Twitter thread + tag relevant accounts (@simonw, @swyx, dev tooling
  Twitter influencers).
- 12:30 — Indie Hacker post.
- 13:00 — Reddit r/selfhosted + r/ClaudeAI.
- 14:00 — Email sequence email 3 trigger.
- Akşam 18:00–24:00 UTC — yorumları yanıtla (HN/Reddit, response within 1h
  sıralamayı yukarı çeker).
- Ertesi sabah — eklenen satışlar/demo sayıları + `billing_status` raporu.

### 3.3 Common HN/Reddit soruları (önceden hazırlık)

- "Why not just use [LangChain/LiteLLM]?"  
  → ABS Claude Code-native (MCP-first), provider cascade circuit breaker.
- "What's the minimum hardware?"  
  → 1 vCPU, 1 GB RAM (SQLite + uvicorn). VPS $5/ay.
- "Open source mı?"  
  → Apache 2.0 core, premium add-ons (advanced RAG, team panel) kapalı.
- "Anthropic TOS sorun mu?"  
  → Hayır, ABS sadece kullanıcı kendi key'i ile orchestrate ediyor; promptlar
    Anthropic'e doğrudan gidiyor (man-in-middle yok).

---

## Faz 4 — Post-Launch İzleme (Hafta 6+)

### 4.1 Success metrics

| Metrik | Hedef (ay 1) | Hedef (ay 3) |
|---|---|---|
| Waitlist signup | 200 | 1000 |
| Demo başlatma | 50 | 250 |
| Lisans satışı | 3 | 15 |
| MRR (one-time + team) | $897 | $4485 |
| Churn (refund) | <5% | <3% |
| HN/Reddit upvote | >50 | — |

### 4.2 Haftalık operasyon (15 dk/gün)

1. `billing_status` MCP tool çağrısı → revenue + license + recent events.
2. Refund/dispute varsa → `docs/billing-runbook.md` § 3-4 izle.
3. Beta tester slack ping: feedback?
4. GitHub issues triaj (her 2 günde bir `beta` label'lı issue'ları kapat).
5. `health_status` (014) check — provider uptime <%99 ise alert.

### 4.3 Aylık retro

- Refund nedenleri çıkar (Stripe Dashboard → Disputes/Refunds).
- Demo bırakma noktasını bul (setup wizard adım metrikleri — 022+'a deferred).
- Churn olan müşteri ile 30dk debrief (kalite, fiyat, feature gap?).
- Pricing experiments — 1 SKU'yu 2 hafta $249 dene, conversion rate ölç.

---

## Faz 5 — Beyond First 3 (Hafta 12+)

### 5.1 Müşteri sayısı 10+ olunca

- Customer success email: ay sonu raporu (kullanım, tasarruf, öneriler).
- Annual plan churn 0 olduğunda → testimonial isteği.
- Yıllık retention >85% → case study (uzun blog post).

### 5.2 Pricing power testleri

- Self-Host $299 → $349 (ay 4'ten itibaren, conversion düşüşü <%20 ise kalıcı).
- Team Pack 5 → enterprise tier (10+ seat, $499/ay) eklenir.

### 5.3 Outbound sales (ölçek 50+ müşteri)

- LinkedIn Sales Navigator (10+ dev firma listesi).
- Türkiye'deki yazılım danışmanlık firmaları (>$50K MRR).
- Conference sponsorluk değerlendirme (PyCon TR, NodeSchool).
