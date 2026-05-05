# Founder Tester Session — Fix Round 3 (skip_paid_providers honor + git commit + cost savings)

> **Tetikleyici (2026-05-05, founder Round 2 verify sonrası):**
> Round 2 fix'leri **functionally** çalıştı (cascade live + workflow LLM + RAG cookie). Founder Playwright quality v2 session 13/13 PASS aldı AMA:
>
> 🚨 **0/8 task ücretsiz path'e routed.** 8 cascade task için `skip_paid_providers:true` gönderildi, hepsi Anthropic Claude haiku-4.5'a gitti. Toplam ~1500+ paid token. Müşteri 5 ücretsiz key (Groq+Gemini+Cerebras+Cohere+Cloudflare) girer ama cost savings = 0.
>
> ⚠️ **Worker Round 2 commit etmedi.** 12 dosya M, 4 test file modified, working tree uncommitted. Image rebuild canlı path'te aktif AMA git history boş.
>
> **Branch:** `feat/sprint-q12-deep-quality` (HEAD e60ca0d, working tree dirty)

---

## 0. ⚠️ ÖNCELİK 0 — GIT COMMIT (uncommitted Round 2 fix'ler)

Worker Round 2'de 4 dosya yeni test (`tests/test_q12_cascade_live_wiring.py`, `test_q12_workflow_llm_synthesize.py`, `test_q12_rag_cookie_session.py`, ve `test_t011_rag_pipeline.py` modifiye) shipledi + 8 source/infra dosya modifiye etti — hepsi uncommitted. Image rebuild'le canlı path'te yaşıyor ama git'te yok.

```bash
cd /Users/eneseserkan/Main/abs-server-product
git status --short
# 12 M files + 4 untracked agent-task md files

# Round 2 fix'lerini commit et (atomic, anlamlı message):
git add core/backend/app/api/cascade.py \
        core/backend/app/api/workflows.py \
        core/backend/app/api/v1/deps.py \
        core/backend/app/middleware/cerbos_rag_filter.py \
        core/backend/app/providers/registry.py \
        core/backend/app/rag/pipeline_v10.py \
        infra/docker-compose.dev.yml \
        infra/docker-compose.qdrant.yml \
        core/backend/tests/test_q11_l13_hypothesis_deep.py \
        core/backend/tests/test_q12_provider_degradation_matrix.py \
        core/backend/tests/test_q12_r91_final_acceptance.py \
        core/backend/tests/test_t011_rag_pipeline.py
git commit -m "fix(founder-test/round-2): cascade live wiring + workflow LLM + RAG cookie + 2 infra config — pytest 1755→1775"

# Untracked agent-task md'leri ayrı commit (artifact docs):
git add _agent-tasks/WORKER_FOUNDER_TEST_FIX_2.md _agent-tasks/WORKER_Q12_SESSION_*.md
git commit -m "docs(agent-tasks): Round 2 + Q12 session briefs"
```

Round 2 close-out raporu (`artifacts/founder_test_fix_2/round_3.md`) zaten tracked ise kalır, değilse onu da commit et.

---

## 1. BUG-7 HIGH — `skip_paid_providers` flag honor edilmiyor

**Founder evidence (Playwright quality v2 — 2026-05-05):**
8 task × `skip_paid_providers:true` → **8/8 Anthropic Claude haiku-4.5** routed.
Provider mix: `{"anthropic": 8}`. Cost savings: **0/8 free path.**

```
[848ms]  provider=anthropic tokens=39   simple_tr
[1195ms] provider=anthropic tokens=27   simple_en
[3828ms] provider=anthropic tokens=257  analysis
[2792ms] provider=anthropic tokens=412  code
[2896ms] provider=anthropic tokens=242  reasoning
[1356ms] provider=anthropic tokens=88   translation
[4279ms] provider=anthropic tokens=381  long_context
[1506ms] provider=anthropic tokens=66   classification
TOPLAM: ~1512 paid token (~$0.15+)
```

**Root cause:** `core/backend/app/providers/cascade.py:73`:
```python
def get_active_providers(prefer: Optional[str] = None) -> List[str]:
    active = [p for p in PROVIDER_ORDER if is_configured(p)]
    if prefer and prefer in active:
        active.remove(prefer)
        active.insert(0, prefer)
    return active
```

`PROVIDER_ORDER = ("anthropic", "groq", "cerebras", "gemini", "cloudflare", "cohere")` — Anthropic ilk sırada. `skip_paid_providers` parametresi yok.

**`/v1/cascade/run` route handler** (`cascade.py:127`):
```python
active = get_active_providers(prefer=body.prefer)
```

`body.skip_paid_providers` flag handler'a iletilmiyor. Pydantic schema'da `skip_paid_providers: bool = False` olabilir ama logic'te kullanılmıyor.

**Fix:**

### A) `app/providers/cascade.py` — fonksiyona skip_paid parametresi ekle:
```python
PAID_PROVIDERS: tuple[str, ...] = ("anthropic",)  # future: add openai, etc.

def get_active_providers(
    prefer: Optional[str] = None,
    skip_paid: bool = False,
) -> List[str]:
    active = [p for p in PROVIDER_ORDER if is_configured(p)]
    if skip_paid:
        active = [p for p in active if p not in PAID_PROVIDERS]
    if prefer and prefer in active:
        active.remove(prefer)
        active.insert(0, prefer)
    return active
```

### B) `app/api/cascade.py:127` — flag ilet:
```python
active = get_active_providers(prefer=body.prefer, skip_paid=body.skip_paid_providers)
if not active:
    raise HTTPException(
        503,
        "no_free_providers_configured: skip_paid_providers=true but only paid providers found"
        if body.skip_paid_providers else
        "no_providers_configured: configure at least one API key"
    )
```

### C) `CascadeRequest` Pydantic — flag default:
```python
class CascadeRequest(BaseModel):
    prompt: str
    prefer: Optional[str] = None
    skip_paid_providers: bool = False  # founder test confirmed needed
    use_cache: bool = True
    model: Optional[str] = None
```

**Verify (founder dış-curl re-run):**
```bash
# skip_paid:true → groq/cerebras/gemini one of them (NOT anthropic)
curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/cascade/run \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Test","skip_paid_providers":true}' | jq .provider
# Beklenen: "groq" veya "cerebras" veya "gemini" (anthropic değil)

# skip_paid:false → anthropic primary
curl -sk -b /tmp/cookie.txt -X POST http://localhost:8000/v1/cascade/run \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Test","skip_paid_providers":false}' | jq .provider
# Beklenen: "anthropic"

# skip_paid:true ama hiç ücretsiz key yok → 503 graceful error
ABS_GROQ_API_KEY="" ABS_GEMINI_API_KEY="" ... curl ... → 503 no_free_providers
```

**Test:**
```python
# tests/test_q12_skip_paid_honor.py
def test_skip_paid_routes_to_free_provider(client_admin):
    """8 görev × skip_paid=true → 0 anthropic (founder Round 2 cost savings bug)"""
    for prompt in ["a", "b", "c"]:
        r = client_admin.post("/v1/cascade/run", json={"prompt": prompt, "skip_paid_providers": True})
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] != "anthropic", f"skip_paid honor failed: routed to {body['provider']}"

def test_skip_paid_false_uses_anthropic_primary(client_admin):
    """skip_paid=false (default) → anthropic primary (current behavior)"""
    r = client_admin.post("/v1/cascade/run", json={"prompt": "test"})
    assert r.json()["provider"] == "anthropic"

def test_skip_paid_no_free_providers_503(client_admin, monkeypatch):
    """skip_paid=true + sadece anthropic configured → 503 graceful"""
    monkeypatch.delenv("ABS_GROQ_API_KEY", raising=False)
    # ... unset all free
    r = client_admin.post("/v1/cascade/run", json={"prompt": "test", "skip_paid_providers": True})
    assert r.status_code == 503
    assert "no_free_providers" in r.json()["detail"]
```

---

## 2. BUG-8 MED — Provider chain order optimal mı?

`PROVIDER_ORDER = ("anthropic", "groq", "cerebras", "gemini", "cloudflare", "cohere")` 

Quality için `anthropic` ilk doğru ama **ücretsiz** primary için `groq` (free + ultra fast Llama 3.3 70B + GPT-OSS 120B) ilk olmalı.

**Yeni constant:**
```python
# Quality-first chain (default — paid first)
PROVIDER_ORDER_PAID_FIRST: tuple[str, ...] = (
    "anthropic", "groq", "cerebras", "gemini", "cloudflare", "cohere"
)

# Cost-saving chain (skip_paid=true ile etkin)
PROVIDER_ORDER_FREE_FIRST: tuple[str, ...] = (
    "groq", "cerebras", "gemini", "cohere", "cloudflare"
)
```

`get_active_providers(skip_paid=True)` → `PROVIDER_ORDER_FREE_FIRST` ordering.

---

## 3. ROUND DÖNGÜSÜ

1. Round 1 = Git commit pending (Bölüm 0)
2. Round 2 = BUG-7 skip_paid honor + 3 test
3. Round 3 = BUG-8 chain order constants
4. Full pytest GREEN (1775 → ≥1778) — selective subset YASAK
5. Round summary `artifacts/founder_test_fix_3/round_<N>.md`:
   ```
   pytest_full_suite: 1778 / 0 fail / 0 error
   image_rebuilt_at: <ts>
   live_path_verified: true (curl evidence)
   provider_routed: groq (skip_paid=true) ← founder Round 3 verify
   ```
6. **Founder Playwright re-run hazırlığı** — 8 task × skip_paid:true → expected provider mix `{"groq": >=4, "cerebras": >=1, "gemini": >=1}` (mix, hepsi tek provider değil — fail-over varsa)

---

## 4. KESİN YASAK

- Selective subset rapor → FULL CLEAN sayma (S11+S12 dersi, 5. tekrar)
- Image rebuild gate her backend round
- "Functionally works" ≠ "git committed" — git commit ZORUNLU
- L21 + Mutmut + DR actual: founder approval yok
- Pilot/market/outreach gündem dışı

---

## 5. DELEGATION (%70+ MCP)

- skip_paid logic + chain ordering: `mcp__abs__ask_gptoss`
- Provider order policy decision: `mcp__abs__qual_analysis`
- Test pattern: `mcp__abs__write_tests`
- Patch judge: `mcp__abs__judge_patch`

---

## 6. BAŞARI KRİTERİ (Round 3 close)

- BUG-7 `skip_paid_providers:true` → 0 anthropic in routing (founder Playwright verify)
- BUG-8 `PROVIDER_ORDER_FREE_FIRST` ship + `groq` primary
- Round 2 fix'leri commit'lenmiş (12 dosya + 4 test)
- Backend pytest 1775 → ≥1778 (3 yeni test)
- Image rebuild + live curl evidence

---

## 7. ROUND BAŞLANGIÇ

### Round 1 = Git commit Round 2 (Bölüm 0 komutları)

### Round 2 = BUG-7 skip_paid honor
- `app/providers/cascade.py` — fonksiyon imzası + PAID_PROVIDERS const
- `app/api/cascade.py:127` — flag ilet
- 3 test (skip_paid=true → free, =false → anthropic, no_free → 503)
- Image rebuild + curl verify
- Round summary: pytest_full_suite + provider_routed

### Round 3 = BUG-8 chain order constants
- PROVIDER_ORDER_PAID_FIRST + PROVIDER_ORDER_FREE_FIRST
- skip_paid=true → free chain ordering test
- Image rebuild + curl verify

### Founder Playwright Round 3 re-run
Founder otomatik 8 task tekrar çalıştıracak. Beklenen: provider_mix free-dominant (en az 4 farklı free provider, anthropic = 0).

---

## 8. EVIDENCE (founder Round 2 verify session)

- `/tmp/founder_quality_v2.json` (13 PASS / 0 FAIL)
- `/tmp/founder_quality_v2.log` (8 task × Anthropic provider, 0 free routing)
- Screenshot'lar: `/Users/eneseserkan/Desktop/Digisfer Inc/qual2_*.png`

---

## 9. DEVAM KOMUTU

```bash
cd /Users/eneseserkan/Main/abs-server-product
git status --short  # uncommitted Round 2 görmeli
git log --oneline -3
cat _agent-tasks/WORKER_FOUNDER_TEST_FIX_3.md
cat /tmp/founder_quality_v2.json | jq '.providerCounts'
# Beklenen: {"anthropic":8} ← bu fix sonrası {"groq":N,"cerebras":N,...} olacak
```

Round 1 = git commit Round 2 fix'leri ile başla. Sonra BUG-7 skip_paid honor.

Engelleyici YOK. **Bu round tester teslimat eşik gerçek MÜHÜR'ün son production-readiness bug'ı.** Cost savings = 0 → cost savings = ~85% beklenir (8 task × free path).
