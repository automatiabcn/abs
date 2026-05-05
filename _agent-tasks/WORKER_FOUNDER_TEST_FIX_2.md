# Founder Tester Session — Fix Round 2 (Production-readiness gaps)

> **Tetikleyici (2026-05-05, founder Round 1 verify sonrası):**
> 18/18 Round 1 fix verified PASS. Founder devam edip backend cascade + workflow + RAG endpoint'lerini canlı test etti, **3 production-readiness gap** tespit edildi:
> 1. `/v1/cascade/run` → 503 stub (live wiring eksik, Q4 P7-live kaldı)
> 2. `/v1/workflows/synthesize` → template fallback only (LLM bypass)
> 3. `/v1/rag/ingest` → 401 missing_bearer_token (UI'dan token mint pattern eksik)
>
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD e60ca0d, baseline 1755 PASS / 0 / 0)

---

## 0. ⚠️ DOĞRULAMA DİSİPLİNİ (S5+S10+S11+S12 dersleri, 5. tekrarın önüne geç)

Tek doğru pytest komutu — round summary'ye `pytest_full_suite: <X> / <Y fail> / <Z error>` ZORUNLU:
```bash
cd core/backend && ./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py
```

Backend dokunulduğunda **image rebuild** + **container exec** + **dış-curl smoke** ZORUNLU. Round summary'ye `image_rebuilt_at:` + `live_path_verified: true|false`.

**Selective subset rapor → FULL CLEAN sayma.** 4. tekrar yaşadık.

---

## 1. BUG-4 HIGH — `/v1/cascade/run` live wiring eksik (Q4 P7-live)

**Dosya:** `core/backend/app/api/cascade.py:129-135`
**Mevcut davranış:** Provider'lar configured (Anthropic+Groq+Cerebras+Gemini+Cohere=5 active) — endpoint kasıtlı 503 atıyor:
```python
raise HTTPException(
    503,
    "live_cascade_pending: providers configured but live cascade "
    "wiring lands in Q4 Phase 7-live (operator vault key + judge tests). "
    f"Detected chain: {','.join(active)}",
)
```

**Mevcut altyapı:**
- `core/backend/app/cascade/orchestrator.py::call_with_cascade()` ZATEN VAR
  - cache + breaker + provider fallback zinciri
  - `from app.providers.registry import get_provider`
  - `ProviderResponse` döner
- `app/providers/registry.py` — provider classes (Groq, Gemini, Cerebras, Anthropic, Cohere)
- `get_active_providers(prefer=body.prefer)` chain dönüyor

**Eksik olan:** Stub'ı `call_with_cascade()` çağrısı ile değiştirmek.

**Beklenen fix:**
```python
# Replace line 129-136 (the raise stub) with:
primary, *fallbacks = active
try:
    response = await call_with_cascade(
        prompt=body.prompt,
        primary=primary,
        model=body.model,
        fallbacks=fallbacks,
        use_cache=body.use_cache if hasattr(body, 'use_cache') else True,
    )
except ProviderError as exc:
    raise HTTPException(502, f"all_providers_failed: {exc.detail}")

return CascadeResponse(
    text=response.text,
    provider=response.provider,
    model=response.model,
    tokens=response.tokens,
    cached=response.cached,
    latency_ms=response.latency_ms,
)
```

**Verify (founder dış-curl re-run):**
```bash
curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/cascade/run \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Türkiye başkenti nedir? Tek cümle yanıt ver."}' -m 30
# Beklenen: 200 + text + provider in {"groq","gemini","cerebras",...}
```

**Test:**
- `tests/test_q12_cascade_live_wiring.py`:
  - 5 provider mock + each returns mock response → cascade routes to first OK
  - Primary fail (transient) → fallback chain
  - All fail → 502
  - skip_paid_providers=true + only Anthropic configured → 503 no_free_providers
  - Cache hit → cached:true returned

---

## 2. BUG-5 HIGH — `/v1/workflows/synthesize` LLM bypass

**Dosya:** `core/backend/app/api/workflows.py:120-145`
**Mevcut davranış:** Müşteri NL prompt verir → backend keyword match ile sabit template döner. LLM kullanılmıyor.
```python
explanation = (
    f"Template fallback: matched '{best.id}' ({best_score} kw hits). "
    "No LLM key wired — Sprint Q2.CO4 promotes this to a real ragas-judged synth."
)
```

**Beklenen davranış:** LLM çağrısı (cascade üzerinden) NL → JSON workflow synthesize.

**Yapılacak:**
1. `synthesize_workflow_via_llm(intent, locale)` fonksiyonu yaz
2. Prompt: "Generate a workflow JSON matching schema X for intent Y..."
3. `call_with_cascade(prompt, primary=active[0], ...)` ile LLM'i çağır
4. Response JSON parse et → schema validate et
5. Validation fail ise template fallback'e düş + warn log

**Verify:**
```bash
curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/workflows/synthesize \
  -H "Content-Type: application/json" \
  -d '{"intent":"Müşteri toplantı kaydı geldiğinde transcribe et + RAG ingest et + 3 madde Slack özet gönder."}' -m 60
# Beklenen: source!=template, explanation içermez "No LLM key wired"
```

**Test:**
- 3 farklı NL intent (TR/EN/ES) → workflow nodes uygun
- Schema fail → template fallback (warn log emit)
- LLM unavailable → template fallback (graceful degradation)

---

## 3. BUG-6 MED — `/v1/rag/ingest` Bearer token cookie ile çalışmalı veya tenant token mint UI

**Dosya:** `core/backend/app/api/v1/rag.py:rag_action_dep`
**Mevcut davranış:** Cookie session yetmiyor — Bearer token (MCP/tenant token) gerekli. Founder local test'te 401 missing_bearer_token aldı.

**İki yol:**
- **A) Cookie-from-cookie token mint:** Admin cookie session aktifse default tenant token otomatik bind edilsin (UI rahatlığı için)
- **B) UI Bearer token mint sayfası:** `/admin/rag` sayfası açılınca MCP token mint et + localStorage'a koy + fetch'lerde Bearer header kullan

Worker tercih: `B` daha temiz (production multi-tenant pattern). UI'da `useEffect` mount → `POST /v1/admin/mcp-tokens` → Bearer token al → her RAG fetch'te header.

**Verify:**
```bash
# Cookie-from-cookie pattern shipped ise:
curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{"text":"ABS test doc","metadata":{"source":"test"}}' -m 30
# Beklenen: 200 OK
```

UI test (Playwright):
```ts
test('admin/rag page allows ingest without manual token', async ({ page }) => {
  await page.goto('/admin/rag');
  await page.fill('[data-testid="rag-text"]', 'Test document');
  await page.click('[data-testid="rag-ingest"]');
  await expect(page.locator('[data-testid="rag-success"]')).toBeVisible({ timeout: 10000 });
});
```

---

## 4. ROUND DÖNGÜSÜ (5. tekrar disiplini)

1. Bug pick (öncelik: BUG-4 cascade live → BUG-5 workflow LLM → BUG-6 RAG token UX)
2. Root cause + minimal fix (orchestrator zaten var, sadece wire et)
3. **Image rebuild + container exec + dış-curl smoke** (per backend round)
4. Yeni test (yukarıdaki spec'ler PASS)
5. **Full pytest GREEN** (selective subset YASAK — 4. tekrarın önüne geç)
6. Round summary `artifacts/founder_test_fix_2/round_<N>.md`:
   ```
   pytest_full_suite: <X> / 0 fail / 0 error
   image_rebuilt_at: <ts>
   live_path_verified: true (curl evidence)
   ```

---

## 5. BAŞLANGIÇ ROUND'LARI

### Round 1 = BUG-4 cascade live wiring
- `app/api/cascade.py:129-135` stub → `call_with_cascade()` çağrısı
- 5 yeni test (mock provider + cascade chain + cache + skip_paid)
- Dış-curl: `/v1/cascade/run` 200 + provider + tokens
- Image rebuild + container exec verify

### Round 2 = BUG-5 workflow LLM synthesize
- `app/api/workflows.py:120-145` template fallback → LLM-first + template fallback
- 3 yeni test (TR/EN/ES + LLM unavailable graceful)
- Dış-curl: source!=template

### Round 3 = BUG-6 RAG token UX
- `/admin/rag` UI auto-token mint OR cookie-from-cookie tenant default token
- Playwright test (Bearer manual ship YOK → ingest works)
- UI verify

### Round 4 = Final founder Playwright re-run hazırlığı
- 4 endpoint live (chat zaten ✅ + cascade + workflow + rag)
- Provider degradation matrix UI'dan test edilebilir
- Founder /resume + Playwright headed session

---

## 6. KESİN YASAK

- Selective subset rapor → FULL CLEAN sayma (S11 dersi, 4. tekrar; 5. olmasın)
- "Shipped + test PASS standalone" ≠ "live path works"
- Image rebuild gate her backend round
- Mock LLM ile gerçek cascade simüle etme — gerçek provider key'ler env'de var, gerçek HTTP call yap
- L21 + Mutmut + DR actual: founder approval yok
- Pilot/market/outreach gündem dışı

---

## 7. DELEGATION ZORUNLU (%70+ MCP)

- Cascade orchestrator wiring: `mcp__abs__ask_gptoss` (call_with_cascade integration pattern)
- LLM workflow synth + JSON schema validation: `mcp__abs__ask_kimi`
- Bearer token UX (Next.js Bearer fetch wrapper): `mcp__abs__ask_kimi`
- A11y/i18n TR/EN/ES error messages: `mcp__abs__ask_qwen32b`
- Code review per fix: `mcp__abs__code_review tier=standard`
- Patch judge: `mcp__abs__judge_patch`

---

## 8. BAŞARI KRİTERİ

- BUG-4 `/v1/cascade/run` 200 dış-curl ile gerçek provider response (founder verify)
- BUG-5 `/v1/workflows/synthesize` source!=template (LLM-based)
- BUG-6 `/admin/rag` UI'dan ingest+query manual token YOK
- Backend pytest 1755 → ≥1755 (regresyon yok, +8-10 yeni test)
- Image rebuild + live_path_verified evidence per backend round
- 0 fail + 0 error full suite

---

## 9. ENV (founder hazır)

- Backend: http://localhost:8000 (image rebuild her round)
- Frontend dev: http://localhost:3457 (worker spawn'da hung self-restart yetkilisin)
- Cookie üret:
  ```bash
  curl -sk -c /tmp/cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}'
  ```
- 9 provider key live in container env (founder verified earlier)

---

## 10. EVIDENCE (founder Round 1 verify session)

- /tmp/founder_quality_test.json (8 test, 3 PASS / 5 FAIL — 5'in 4'ü endpoint name yanlışı, biri gerçek auth gap)
- /tmp/founder_quality_test.log (full session log)
- /Users/eneseserkan/Desktop/Digisfer Inc/qual_*.png (screenshots)
- Dış-curl evidence (yukarıdaki cascade 503 + workflow template = founder shell session)

---

## 11. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -5
cat _agent-tasks/WORKER_FOUNDER_TEST_FIX_2.md
cat /tmp/founder_quality_test.json
```

Round 1 = BUG-4 cascade live wiring'den başla. `call_with_cascade()` zaten var, sadece route'a wire et. 5 yeni test + image rebuild + dış-curl evidence.

Engelleyici YOK. **Bu round'lar tester teslimat eşik gerçek MÜHÜR'ün önündeki son production-readiness gap'leri kapatıyor.**
