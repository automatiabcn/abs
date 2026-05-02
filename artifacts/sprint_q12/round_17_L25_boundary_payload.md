# Q12 — Round 17 — L25 boundary payload

**Tarih:** 2026-05-03
**Layer:** L25 — boundary payload (Q12 Session 2 yeni, 5/5 yeni layer)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx)

---

## 0. Hedef

Brief talebi:
- RAG ingest 25MB
- chat session 1000 msg
- workflow 100 nodes
- plugin install 50MB

Audit gerçek deklare cap'leri ortaya çıkardı (post-Sprint 19+):

| Endpoint | Field | Pre-Round 17 cap |
|----------|-------|------------------|
| POST /v1/rag/ingest | text | 2_000_000 chars (~2 MB) |
| POST /v1/rag/ingest | contextual_prefix | 4_000 chars |
| POST /v1/rag/query | query | 4_000 chars |
| POST /v1/chat/sessions | title | 200 chars |
| POST /v1/chat/completions | content (per msg) | 8_000 chars |
| POST /v1/workflows/synthesize | intent | 2_000 chars (min 10) |
| POST /v1/marketplace/install | plugin_id, tenant | **UNBOUNDED — Q12-L25-001!** |

Brief'in büyük rakamları (25MB, 50MB) explicit DoS surface ölçeğindeydi;
real declared cap'ler daha sıkı. L25 kontratı: "real cap enforced VE
over-cap path 422 (validation error) döner — 500 OOM veya 200 silent
truncation yok".

---

## 1. Bulgu — Q12-L25-001 (HIGH security + DoS)

**Lokasyon:** `core/backend/app/api/marketplace.py:146`

```python
# pre-fix
class InstallBody(BaseModel):
    plugin_id: str               # ← UNBOUNDED — 1 MB+ accepted
    tenant: str = "default"      # ← UNBOUNDED — path traversal
```

**Risk:**
1. **DoS**: adversary POST plugin_id=`"a" * 1_000_000` → registry
   lookup linear scan + state file persist with 1 MB row.
2. **Path traversal**: `tenant` field downstream filesystem path
   construct'a girer (install handler tenant-scoped dir oluşturur).
   `tenant="../../../etc"` ile escape açılabilir.
3. **Shell metachar injection**: `plugin_id="evil;rm -rf /"` veya
   `evil$(date)` cosign signature verification kabukundan
   geçerse (Sprint 19 plugin manifest cosign verify), shell
   exec context'inde komuta dönüşebilir.

**Reprodüksiyon (git stash ile kanıtlandı):**

```
core/backend/tests/.../TestQ12L25MarketplaceInstallBoundary
  test_oversized_plugin_id_rejected  → assert 404 == 422  ❌
  test_path_traversal_tenant_rejected  → assert 404 == 422  ❌
  test_shell_metachar_plugin_id_rejected  → assert 404 == 422  ❌
```

3/4 test FAIL pre-fix. (4. test = "safe id" → 404 plugin missing,
which is post-validation; Pydantic accepted the input.)

**Fix (shipped):**

```python
class InstallBody(BaseModel):
    plugin_id: str = Field(
        ..., min_length=1, max_length=128,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    tenant: str = Field(
        default="default",
        min_length=1, max_length=64,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
```

`pattern` allowlist + `max_length` cap. Tüm 3 saldırı vektörü
deterministic 422.

---

## 2. Tests — `core/backend/tests/test_q12_l25_boundary_payload.py` (14 test)

```
TestQ12L25MarketplaceInstallBoundary (4):
  oversized_plugin_id_rejected         ← 200-char (>128)        → 422
  path_traversal_tenant_rejected       ← "../../../etc"        → 422
  shell_metachar_plugin_id_rejected    ← ";rm","`whoami`","$()"→ 422
  safe_plugin_id_passes_validation     ← "abs.demo_plugin-v1" ≠ 422

TestQ12L25RagIngestBoundary (5, Pydantic-direct since cerbos JWT):
  ingest_text_under_cap_accepted        ← 2_000_000 char OK
  ingest_text_over_cap_rejected         ← 2_000_001 → ValidationError
  query_under_cap_accepted              ← 4_000 OK
  query_over_cap_rejected               ← 4_001 → ValidationError
  contextual_prefix_over_cap_rejected   ← 4_001 → ValidationError

TestQ12L25WorkflowSynthesizeBoundary (3, login then HTTP):
  intent_at_cap                         ← 2_000 ≠ 500
  intent_over_cap_returns_422           ← 2_001 → 422
  intent_under_min_returns_422          ← "short" (<10) → 422

TestQ12L25WorkflowExecuteNodesGraceful (2):
  100_node_workflow_no_500              ← 100 noop nodes ≠ 500
  empty_nodes_returns_400               ← {nodes:[]} → 400/422
```

**Sonuç:** 14/14 PASS post-fix · 3/4 marketplace test FAIL pre-fix.

---

## 3. Pin / negative-finding olarak dokümante

Bunlar zaten enforced — Round 17 tarafından test ile pin edildi:

- RAG ingest text 2 MB cap
- RAG ingest contextual_prefix 4 KB
- RAG query 4 KB
- Workflow synthesize intent 10–2000 char
- Chat session title 200 char (henüz test ile pin edilmedi; geriye-uyum
  guard'ı yeterli)
- Chat completion message 8 KB (aynı; chat router test'leri kapsıyor)

---

## 4. Layer state

| Layer | Counter | Notes |
|-------|---------|-------|
| **L17** | **3/3 ⭐** | bundle break-even validator + unit + CI gate |
| **L18** | **3/3 ⭐** | cold-cache + CDP throttle 12/12 PASS |
| **L19** | **3/3 ⭐** | backwards compat 11/11 + 1473 full suite PASS |
| **L20** | **3/3 ⭐** | chaos 5/5 PASS (redirect-loop fix) |
| **L21** | **1/3** | fresh-deploy drill (safe variant 3/3 PASS) |
| **L22** | **1/3** | race condition fix (setup wizard TOCTOU) |
| **L23** | **1/3** | observability fix (req_id + emit_event) |
| **L24** | **1/3** | secret leakage fix (magic_token + Stripe) |
| **L25** | **1/3** | boundary payload fix (marketplace + 14/14 PASS) |
| **L26** | **1/3** | JWT lifecycle hardening (typed exceptions) |

**5/5 Q12 Session 2 yeni layer 1/3'e ulaştı** (Session 2 hedefi: en az
1/3 her biri). Session 2 başarı kriteri ✓.

---

## 5. Atomic commit

```
fix(q12/L25): Round 17 marketplace InstallBody hardening + Pydantic boundary pins — 14/14 PASS (3/4 fail pre-fix proven)
```
