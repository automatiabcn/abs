# Pazar Araştırması Özeti

_Kaynak: Apr 23 oturumunda gemini_search ile 4 query. Raw sonuçlar memory'de._

## 1. Pazar Büyüklüğü

- **AI orchestration:** $12.3B (2025) → $13.7B (2026). CAGR ~11%.
- **AI gateway:** $4.3B (2025) → $4.9B (2026).
- **Terminal-based AI dev tools** hızlı büyüyen niş (Claude Code, Cursor CLI, Aider, Cline).
- **Anthropic Claude Marketplace (B2B)** Mart 2026 açıldı — kurumsal Claude tool dağıtım kanalı.

## 2. Rakip Haritası

### Direkt rakip YOK
Hiçbir rakip "Claude Code'u genişleten + $20 plan'ı optimize eden + multi-provider free tier kullanan" konumda değil. Bu ABS'nin boş nişi.

### Dolaylı rakipler
| Rakip | Ne yapar | Neden ABS rakip değil |
|---|---|---|
| **LiteLLM** | OpenAI-format provider proxy | Sadece format dönüşüm; hook/RAG/judge/panel yok |
| **Aider** | Terminal AI coding tool | Claude Code **alternatifi**; MCP server olarak ABS'ye tool olabilir |
| **Cline / Roo Cline** | VS Code extension | IDE-bound; ABS terminal-first |
| **Cursor CLI** | Cursor IDE + cloud | IDE + managed; ABS self-host + any editor |
| **Dify** | Low-code agent+RAG platform | Drag-drop UI; ABS code-first developer tool |
| **FlowiseAI** | Low-code LLM app builder | Non-technical target; ABS developer target |
| **Vercel AI Gateway** | Production app proxy | Web app için; ABS dev workflow için |
| **n8n AI** | Workflow automation | General purpose; ABS code-specific |

### Enterprise rakipler
- **Sourcegraph Cody** — code intelligence + enterprise VPC
- **Tabnine** — enterprise self-host + CI/CD
- **Codeium / Windsurf** — enterprise self-host option

Bunlar Claude Code değil, **alternatif**. ABS'nin Claude Code üzerine inşa olması onlardan farklı.

## 3. Deployment Trendleri (2026)

**Kazanan model:** Docker Compose + Coolify/Dokploy PaaS + otomatik SSL (Caddy/Traefik)

**Kaybeden model:** Baremetal install script (bağımlılık cehennemi, müşteri yoruluyor)

**Indie/10-50 firma için Kubernetes overkill** — "karmaşıklık vergisi".

**Self-hosted + MoR (Merchant of Record) SaaS** = 2026 indie hacker default:
- **Lemon Squeezy** (Stripe tarafından 2024'te satın alındı) — global tax otomatik
- **Paddle** — alternatif MoR, fee biraz daha yüksek
- **Stripe direkt** — tax compliance kullanıcının sorumluluğu

## 4. Open-Core Pricing Benchmark

| Şirket | Model | Örnek fiyat |
|---|---|---|
| **Supabase** | Resource-based freemium | Free: 500MB DB + 50K MAU, Pro: $25/ay |
| **PostHog** | Usage-based freemium | Free: 1M events/ay, sonra usage |
| **n8n** | Self-host free + Cloud paid | Self-host: unlimited, Cloud: $20/ay+ |
| **Appsmith** | Feature-gated freemium | Free: 5 user, Business: $15/user/ay, Enterprise: $2500/ay (100 user = $25/user) |
| **Cal.com** | Freemium + Cloud | Free: basic, Teams: $15/user/ay |

**Benchmark çıkarım:**
- Community (free self-host) viral adoption kanalı
- Business $15-30/user/ay sweet spot
- Enterprise $2000-5000/ay custom

**ABS öneri:** Business $29/user/ay (Appsmith + Cal.com ortalaması + premium özellik)

## 5. Enterprise Satın Alma Süreci (2026)

**CTO/VP Eng karar kriterleri:**
1. Security certifications (SOC 2 Type II, GDPR, HIPAA where relevant)
2. Data residency (self-host veya VPC)
3. SSO (Google, Okta, Azure AD)
4. Audit log + RBAC
5. SLA + dedicated account management
6. Case studies (real-world success)

**PoC süreci:** 40% daha hızlı 2026'da, ama security review + legal review hâlâ gerekli.

**Küçük bağımsız vendor'un enterprise'a girme yolu:**
1. Open-source adoption (GitHub stars, community)
2. Strong docs + case studies
3. Self-serve pricing → upsell Business → yeterli traction → Enterprise satış
4. Security audit (independent) ileride zorunlu

## 6. Personal AI Stack Marketplace Durumu (2026)

**Mevcut kanallar:**
- **OpenAI GPT Store** — özel GPT'ler, revenue share programı
- **Anthropic Claude Marketplace (B2B)** — Mart 2026 açıldı, kurumsal dağıtım
- **Claude Code Skills Marketplace** — GitHub tabanlı, community
- **Anthropic MCP Hubs** — topluluk kürasyonu, MCP server dizinleri
- **Cursor Marketplace** — plugins + rules + hooks
- **Raycast Extension Store** — AI uzantılar

**Bizim için:** ABS **tek başına ürün** olacak, yukarıdaki kanallara "dağıtılacak" değil (onlar ABS'nin aracı olmaz, ABS onları aracı olarak kullanır). İleride Anthropic Claude Marketplace'e girebiliriz (2027 planı).

## 7. Payment Processor

| Platform | Kim için | Fee | MoR |
|---|---|---|---|
| **Lemon Squeezy** | Indie hacker, solopreneur | 5% + 50¢ | ✅ Global tax |
| **Paddle** | Solopreneur + B2B | 5% + 50¢ | ✅ 200+ market |
| **Stripe** | Developer-first, kontrol isteyenler | 2.9% + 30¢ | ❌ (Atlas ile kısmi) |

**MVP öneri:** **Lemon Squeezy** — MoR ile tax yok, kurma hızlı, Stripe acquired (gelecek garanti).

## 8. Key Takeaways — ABS İçin Strateji

1. **Direkt rakip yok** — ilk mover advantage
2. **Claude Code extension olarak konumlan** — "replace" değil "enhance"
3. **Open-core + Apache 2.0** — büyük firma legal review güvenli
4. **Business $29/user/ay** — benchmark aligned
5. **LS + self-host free** — indie default
6. **Docker Compose + Caddy** — deployment kolaylığı
7. **Enterprise SOC 2/SSO** — ileride (yıl 2) zorunlu hale gelir
