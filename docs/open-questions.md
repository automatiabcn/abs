# Açık Kritik Sorular

_Bu soruları cevaplamadan `core/` kodu yazmaya geçmiyoruz. Yanlış yönde kod üretme riski var._

Sıra önem sırasına göre — **1'den başla**.

## 1. Anthropic TOS (🚨 KRİTİK — LEGAL)

**Soru:** Claude Pro $20 plan'ı orchestration layer (ABS) üzerinden çağırmak Anthropic Terms of Service'e uygun mu?

**Araştırılacak:**
- Anthropic Terms of Service + Usage Policy tam okuma
- Claude Pro "personal use" mu, "team use" mu onaylıyor?
- MCP tool üzerinden çoklu kullanıcı plan paylaşımı yasal mı?
- Enterprise plan'a yönlendirme şartı var mı?

**Neden kritik:** Eğer Anthropic "$20 plan'ı orchestrate eden üçüncü taraf tool" yasaklıyorsa, ürün hukuken sıfırdan başlamalı. Satış öncesi netleşmeli.

**Nasıl cevaplarız:**
- Anthropic Support'a resmi soru
- Reddit r/ClaudeAI + Anthropic forum + GitHub issues tarama
- Legal review (ileride, paid müşteri öncesi)

## 2. Ürün Adı

**Soru:** "ABS" kalır mı? Alternatifler değerlendirilecek mi?

**Opsiyonlar:**
- **ABS** — kısa, hafıza güçlü, ama arabada "anti-lock braking" ile karışır, anlamı belirsiz
- **AutomatiaBCN Stack** — kişisel marka ile bağ
- **StackForge** — "stack kurma" çağrışımı
- **Stackward** — şirket-merkezli ton
- **Hivemind** — AI koleksiyonu çağrışımı (AWS'de bir iş ismi var)
- **Pipeline Forge** — mühendislik tonu
- **Clio / Clarity / Cipher** — tek kelime marka denemesi

**Karar kriteri:**
- Domain müsait mi (.dev, .ai, .io)
- Trademark (USPTO, EU IPO) çakışması
- Pronunciation (telefonda söylenirken net mi)
- SEO (Google'da "ABS" çok kelime, "StackForge" gibi tek)

## 3. Revenue Model Final Karar

**Mevcut tavsiye:** Apache 2.0 open-core + 3 tier subscription (Community free + Business $29/user/ay + Enterprise custom)

**Alt kararlar:**
- Hangi feature'lar **community** (free)?
- Hangi feature'lar **Business** (paid)?
- Hangi feature'lar **Enterprise** (custom)?

**Örnek ayrım (taslak):**
| Feature | Community | Business | Enterprise |
|---|---|---|---|
| 75 MCP tool | ✓ | ✓ | ✓ |
| Hook sistemi | ✓ | ✓ | ✓ |
| Quality pipelines | ✓ | ✓ | ✓ |
| Basic panel | ✓ | ✓ | ✓ |
| Single user | ✓ | ✗ | ✗ |
| Multi-user auth | ✗ | ✓ | ✓ |
| SSO (Google, Okta) | ✗ | ✗ | ✓ |
| Audit log export | ✗ | ✓ | ✓ |
| RBAC (role-based) | ✗ | ✗ | ✓ |
| White-label | ✗ | ✗ | ✓ |
| Priority support | ✗ | ✓ | ✓ |
| On-site training | ✗ | ✗ | ✓ |
| SLA | ✗ | ✗ | ✓ |

## 4. Gelir Hedefi

**Soru:** Aylık kaç $ gelir hedef? (Bu müşteri sayısını belirler.)

**Hesap:**
- $5K/ay = 7 Business müşteri (25 user avg)
- $10K/ay = 14 Business müşteri
- $20K/ay = 28 Business müşteri (solo tavanı)
- $30K+/ay = ekip büyütme kararı

**Ek soru:** Automatiabcn Stack ürünü ek gelir kanalı olacak mı, yoksa bu senin primary business'in?

## 5. İlk Müşteri (Go-to-Market)

**Soru:** İlk 3 müşteriyi nereden bulacağız?

**Kanal opsiyonları:**
- **Product Hunt launch** (viral potansiyel, tech audience)
- **Hacker News "Show HN"** (engineering audience, TL;DR video + demo)
- **Twitter/X build-in-public** (30 gün geliştirme sürecini paylaş)
- **LinkedIn outreach** (10-50 kişilik firma CTO'larına direct mesaj, 50-100 mesaj/hafta)
- **Dev.to / Medium yazı dizisi** ("How I built orchestration layer for Claude Code")
- **Reddit r/ClaudeAI + r/selfhosted** (topluluk-odaklı)

**Senin mevcut network:**
- Automatiabcn kanalları (Twitter, Indie Hacker community)
- Yaratılabilecek "early access list" (landing page waitlist)

## 6. Legal Entity

**Soru:** Fatura/ödeme için hangi ülke üzerinden?

| Opsiyon | Artıları | Dezavantajları |
|---|---|---|
| **Türkiye firması** | Türk müşteri rahat | Uluslararası fatura zor (FX + SWIFT) |
| **İspanya / BCN** | AB uyumlu (KDV rahat), Automatiabcn BCN markası | Kurma maliyeti orta |
| **Delaware C-corp** | VC hazır, Stripe/LS full support | Kurma pahalı ($500+), Türkiye ikametgah + vergi karmaşık |
| **Lemon Squeezy üzerinden (MoR)** | Hemen başla, LS senin fatura/tax'ını halleder | Revenue share (~%5) |

**MVP öneri:** Önce **Lemon Squeezy Merchant of Record** ile başla (legal entity kurma öncesi). ARR $50K+ olunca Delaware C-corp düşünülür.

## 7. Delegation Quota Edge Cases

**Soru:** Müşteri Cohere 1000/ay veya Gemini 1500/gün free tier'ını bitirdiğinde ne olur?

**Opsiyonlar:**
- **A) Hard cap** — o provider devre dışı, diğerlerine fallback
- **B) Paid tier uyarısı** — "Upgrade to Gemini Paid ($X/M token)" panel banner
- **C) Otomatik downgrade** — Claude'a yönlen (ama Claude token tüketir, amaç sapar)

**Tavsiyem:** A + B kombinasyonu. Panel'de real-time provider budget alerts (E15 Cohere pattern'ini 6 provider'a genişlet).

---

## Karar Matrisi (sonraki oturum için)

| Soru | Durum | Beklenen |
|---|---|---|
| 1. Anthropic TOS | ⏸ Açık | Legal araştırma + Anthropic support ticket |
| 2. Ürün adı | ⏸ Açık | 5 aday arasında seçim + domain check |
| 3. Revenue model | ⏸ Tavsiye var, onay bekliyor | Kullanıcı karar |
| 4. Gelir hedefi | ⏸ Açık | Kullanıcı $/ay hedef |
| 5. Go-to-market | ⏸ Açık | 1-2 kanal seçimi + MVP sonrası plan |
| 6. Legal entity | ⏸ MVP için LS önerisi | Kullanıcı onay |
| 7. Quota edge cases | ⏸ Tavsiye var | Kullanıcı onay |
