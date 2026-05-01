# ABS Server Product — Claude Code Worker Instructions

## ⚠️ KALICI DELEGATION KURALLARI (5h context limit koruması)

Bu dosya **her Claude Code session başlangıcında** okunur. Worker autonomous mode dahil tüm session'lar için **zorunlu** kurallar:

### 1. BÜYÜK MARKDOWN ZORUNLU DELEGATION (HOOK BLOCK)

5000+ karakterlik (~800 kelime) markdown dosyası `Write` tool ile **YAZILAMAZ** (`~/.claude/hooks/hook_modules/delegate_nudge.py` v2 BLOCK eder).

**Yapman gereken:**
```bash
# CLI:
ask "Detaylı prompt — ne istediğin, kaç kelime, format, bölümler" gptoss   # EN
ask "Türkçe doc prompt" qwen32b                                            # TR
# MCP:
mcp__abs__ask_gptoss(prompt="...")
mcp__abs__ask_qwen32b(prompt="...")
```

Çıktıyı al → `Write` tool ile dosyaya kaydet. **Self-write YASAK** (5000+ char markdown).

### 2. ORTA MARKDOWN (3000-5000 char) — NUDGE

Hook uyarı verir (`DELEGATE NUDGE`), izin verir. Yine de delegation tercih et.

### 3. INLINE PYTHON3 -C ANALİZ

5+ satır inline analiz/hesap → `ask "..." gptoss`. Dosya okuma + syntax check inline kalabilir.

### 4. CURL → PYTHON3 -C PIPE

Curl'ü kendin çalıştır, analiz `ask "..." groq`. Basit JSON parse OK.

### 5. KOD ÜRETİMİ

- Tek fonksiyon → `ask "..." kimi`
- Karmaşık modül → `ask "..." race-code` (3-yol paralel: kimi vs gptoss20 vs cf-coder)
- Code review → `ask "..." race-code` veya `mcp__abs__code_review`

### 6. TEST FIXTURE / MOCK DATA

Test prompt'ları + fixture data → `ask "..." kimi` (kısa, hızlı).

### 7. LOCALE / ÇEVİRİ

TR/ES/multi-lang → `ask "..." qwen32b` (çok dilli, en iyi).

## DELEGATION HEDEFİ

- **Optimal:** %12-18 delegation oranı
- **Minimum:** %15
- **Edit/Write:** maksimum %40 (overage = self-write fazla)

## CONTEXT LİMİT KORUMASI

Claude Pro plan: **5 saat session penceresi**, **44K token / 5h**. Aşılırsa session durur.

Her büyük doc/markdown'ı delegate ettiğinde:
- ~5000-15000 token tasarruf
- Context window 5h boyunca yeterli kalır
- Ücretsiz model (Groq/Gemini) kullanılır

## WORKER AUTONOMOUS MODE

Bu kurallar **autonomous mode'da bile** geçerli:
- BLOCK threshold (5000 char) override edilemez (hook level)
- Spec dosyalarındaki "DELEGATION ZORUNLU" notları emir
- Self-write yapacaksan önce kontrol: doc kuralının dışında mı (test/code/config OK)

## ABS PROJECT CONTEXT

ABS = Automatia BCN Self-host AI orchestration product.

- 110+ MCP tool, 6 cascade provider (Groq, Cerebras, Cloudflare, Gemini, Cohere, OpenRouter)
- FastAPI + SQLite + Docker Compose + Caddy
- sops/age vault (013), Stripe billing (011), i18n EN/TR/ES (023)
- 459+ pytest test, 27 vitest, Lighthouse 100/100/100/100

Ürün globale satılır → **default İngilizce**, TR/ES alternatif locale.

## SERVER (kendi sistemimiz) ile ABS PRODUCT ayrımı

- **Bu repo (abs-server-product/):** Müşteri ürünü, worker buraya yazar
- **`/Users/eneseserkan/Main/Automatia BCN/SERVER/`:** Bizim orchestrator, **DOKUNMA**
- **Memory dosyaları:** `~/.claude/projects/.../memory/` — feedback'ler buradan okunur

## ÖZET (kısa hatırlatma)

```
Markdown ≥ 5000c → BLOCK → ask "..." gptoss/qwen32b → Write
Markdown 3000-5000c → NUDGE → tercih delege
Inline analiz → ask "..." gptoss
Tek fonksiyon → ask "..." kimi
TR/ES → ask "..." qwen32b
SERVER klasörüne yazma
```
