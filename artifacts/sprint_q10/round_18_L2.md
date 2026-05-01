# Q10 Round 18 — Layer L2 integration enrich

**Tarih:** 2026-05-01
**Branch:** `feat/sprint-q10-quality-loop`
**Commit:** `15fce5a`

---

## Hedef

Round 6'da ship olan 7 contract test happy-path tek endpoint odaklıydı.
Bu round endpoint'leri **birleştirilmiş roundtrip kontratlara** çevirir:
RAG ingest+query roundtrip, cross-tenant block, marketplace install→
list→uninstall lifecycle.

---

## Yeni testler (3)

### TestRagRoundtripAndIsolation (2 test)

#### `test_rag_ingest_then_query_returns_same_doc`

In-memory `_StubQdrant` (dict keyed `(collection, tenant_id) → list`)
ile gerçek embedder + parser + chunker zincirini canlı çalıştırır.
Ingest sonrası aynı tenant query eder, ilk hit'in `doc_id` ingest'in
döndürdüğü ile aynı + text marker'ı içeriyor olmalı.

**Catches:**
- Tenant_id payload'a yazılmazsa → query 0 hit
- Embedder dim mismatch → ensure_collection patlar
- chunker doc_id assignment regression
- search payload field rename (chunk_id, doc_id, seq, text)

#### `test_rag_cross_tenant_query_returns_zero_hits`

Tenant A confidential payload ingest eder, Tenant B aynı kelimelerle
query eder. Hits boş olmalı.

**Catches:**
- Qdrant filter regression (tenant_id payload'da var ama filter
  apply edilmedi)
- JWT audience leak (tenant claim ignore edilirse Tenant B Tenant A'nın
  collection'ını okuyabilir)

OAuth flow + Cerbos allow override + 2 distinct OAuthClient (cid_a,
cid_b) ile ayrı JWT'ler.

### TestMarketplaceLifecycleRoundtrip (1 test)

#### `test_install_then_uninstall_full_lifecycle`

5 adımlı zincir:
1. `POST /v1/marketplace/install` (slack-receiver, default tenant) → 201
2. `GET /v1/marketplace/installed?tenant=default` → `installed[]` slack-receiver içerir
3. `DELETE /v1/marketplace/uninstall/slack-receiver?tenant=default` → 200
4. `GET /v1/marketplace/installed?tenant=default` → `installed[]` slack-receiver içermez
5. Re-DELETE → 404 `not_installed`

**Catches:**
- Install OK ama listing'e yazılmaz (DB write/persistence bug)
- Uninstall OK ama listing'de hayalet kayıt
- Idempotent uninstall regression (404 yerine 200 döner)

Mevcut `test_marketplace_hardening` her adımı izole test eder; bu
test zincir kırılırsa per-step assertion'lar geçse bile fail olur.

---

## İlk attempt + fix (kök neden)

İlk run marketplace test 405 verdi. **Root cause:** `_isolated_install_store`
fixture'i `settings.data_dir` to `tmp_path` set ediyordu, ama session-scope
`_session_data_dir` zaten test session başında bunu set etmişti +
`admin_credentials.json` orada yazılıyor. Function-scope override session
data_dir'ı invalidate etti → bootstrap admin login için credentials
yoksa `/auth/login` 405.

**Fix:** `_isolated_install_store` fixture kaldırıldı, sadece
`_cosign_skip` kaldı. Session data_dir yeterli.

İkinci run 422-shape: response `installed` field değil `items` field
beklendi. Fix: existing `test_marketplace_hardening.py` pattern'iyle
hizalandı (`r.json()["installed"]`).

---

## Sonuç

```
$ pytest tests/test_q10_l2_integration.py
10 passed in 10.80s
```

7 (Round 6) + 3 (Round 18) = 10 PASS, 0 fail, 0 regression.

Backend Q10 toplam test:
- L1 coverage: 22 (18 Round 2/5 + 4 Round 14 token revoke)
- L2 integration: 10 (7 Round 6 + 3 Round 18)
- L1 chat regression: 12 (Q8)
- **Toplam Q10: 44 PASS** (önceki 37 → +4 L6 + +3 L2 = 44)

---

## L2 layer durumu

| Audit hedefi | Round 18 sonu |
|--------------|---------------|
| cascade chain mock-mode roundtrip | ✅ Round 6 |
| panel tools inventory contract | ✅ Round 6 |
| providers status payload | ✅ Round 6 |
| chat session lifecycle | ✅ Round 6 |
| RAG ingest+query single-tenant | ✅ Round 18 |
| RAG cross-tenant zero-leak | ✅ Round 18 |
| marketplace install→list→uninstall lifecycle | ✅ Round 18 |

L2 3-round-clean sayacı: **1/3 → 2/3**.

---

## Atomic commit

`15fce5a` — test(q10/L2): Round 18 — 3 enrichment tests (RAG roundtrip + cross-tenant + marketplace)

Files: 1 test file (+308 lines), 0 source.

---

## Sonraki round

**Round 19 = L1 re-scan, hedef 3/3 (FULL CLEAN ilk layer).**

Round 11'de 37/37 PASS regression-safe doğrulandı. Round 19'da
44 PASS doğrulanır + cov gap (chat_stream send happy path,
Waveform mount, NeuralGraph SSR-skip — backend tarafı gözden geçir).
0 yeni bulgu = L1 FULL CLEAN.

---

**Round 18 status:** ✅ ship — 3 enrichment test PASS, 0 source bug,
0 regression. L2 sayacı 1/3 → 2/3.
