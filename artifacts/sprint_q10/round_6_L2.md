# Q10 Round 6 — Layer L2 Integration Tests

**Tarih:** 2026-05-01
**Branch:** `feat/sprint-q10-quality-loop`

---

## Yeni dosya

`core/backend/tests/test_q10_l2_integration.py` — 7 integration test
4 sınıfta:

### TestCascadeChatRoundtrip (2)
- `test_completions_persists_user_and_assistant_messages` — full SSE
  roundtrip: user message gönder → mock provider yanıt → text + meta
  event'leri parse et → GET messages list user+assistant doğrula →
  GET sessions list message_count ≥ 2 doğrula → cleanup
- `test_cascade_run_direct_returns_mock_provider` — `/v1/cascade/run`
  ABS_ANTHROPIC_MOCK_MODE=ok ile mock=True + provider=anthropic-mock
  + fallback_chain içeriyor

### TestPanelToolsContract (2)
- `test_panel_tools_returns_inventory_shape` — `/v1/panel/tools`
  total + category_counts + tools[] kontrak
- `test_panel_tools_each_row_has_contract_fields` — her tool row name +
  category + description + input_schema.{required, properties}

### TestCascadeProvidersStatus (2)
- `test_providers_endpoint_shape` — `/v1/cascade/providers` 5 zorunlu
  alan: active, missing, configured_count, total, anthropic_mock_mode
- `test_providers_mock_mode_reflected` — autouse fixture ile set edilen
  mock mode response'ta görünüyor

### TestChatSessionLifecycle (1)
- `test_session_create_rename_delete_cycle` — POST → PATCH (title) →
  DELETE → GET messages 404

---

## Sonuç

```
$ pytest tests/test_q10_l2_integration.py
.......                                              [100%]
7 passed, 1 warning in 3.91s
```

Q10 backend test toplam: 12 (Q8 chat) + 18 (L1+L6) + 7 (L2) = **37 PASS**.

---

## Bulgular

Bu round'da kod bug'ı YOK. Mevcut Q8 source'u all 7 contract assertion'u
ilk denemede geçti. Mock mode'da cascade chain temiz, panel tool
inventory contract intact, providers status payload schema-stable.

L2 layer 3-round-clean sayacı: **1/3** (regression-koruma testler
eklendi, sıfır bug).

---

## Regression

- pytest `master_repro.sh phaseA` → 12/12 PASS
- pytest `test_q10_l1_coverage.py` → 18/18 PASS
- pytest `test_q10_l2_integration.py` → 7/7 PASS
- vitest 22/22 PASS
- Q10 backend total: **37 PASS**

---

## Sonraki round

**Round 7 = L3 e2e Playwright** — 15 sayfa × 3 senaryo (login fresh /
empty filter / api-yok) × 2 tema (dark/light). Mevcut spec'ler:
q8-customer-journey (11 step), q10-no-api-degradation (15), q10-a11y-axe
(15). Round 7'de bu 3 spec birlikte koşturulacak + dark+light theme
matrix eklenir.

---

**Round 6 status:** ✅ ship — 7 yeni integration test PASS, 0 bug,
0 regression. L2 sayacı: 1/3.
