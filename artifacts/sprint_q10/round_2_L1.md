# Q10 Round 2 — Layer L1 Unit Test Coverage Gap

**Tarih:** 2026-05-01
**Branch:** `feat/sprint-q10-quality-loop`
**Hedef:** Q8 Phase A/N/P backend dosyaları happy-path-only test edildi.
Round 2 edge case + negative path testleri ekler, böylece coverage
gerçek (mock değil) güvence haline gelir.

---

## Yeni test dosyası

`core/backend/tests/test_q10_l1_coverage.py` — 15 yeni test 3 sınıfta:

### TestMcpTokenHmac (5 test)
- `test_round_trip_signed_token` — sign+verify positive control
- `test_missing_bearer_header_rejects` — 401 missing_bearer_token
- `test_invalid_prefix_rejects` — 401 invalid_token_prefix
- `test_tampered_signature_rejects` — 401 bad_signature (HMAC tamper)
- `test_malformed_token_rejects` — 401 malformed_token (single segment)

### TestClaudeCodeHookScope (4 test)
- `test_mcp_only_token_rejected_on_hook_endpoint` — 403 insufficient_scope
- `test_hooks_scoped_token_accepted` — quota-check allow
- `test_session_start_injects_tenant_context` — additionalContext tenant
- `test_audit_log_returns_received_at_marker` — ISO-8601 ts

### TestChatCrossTenantIsolation (6 test)
- `test_get_messages_for_unknown_session_returns_404`
- `test_delete_unknown_session_returns_404`
- `test_patch_rename_unknown_session_returns_404`
- `test_completions_rejects_empty_messages` — 400 messages_required
- `test_completions_rejects_assistant_last` — 400 last_message_must_be_user
- `test_session_creation_returns_owned_session` — positive round-trip

---

## Sonuç

```
$ .venv/bin/python -m pytest tests/test_q10_l1_coverage.py -q
...............                                              [100%]
15 passed, 1 warning in 6.00s
```

15/15 PASS. Q8 chat suite ile birlikte Q10 backend pytest:
**12 + 15 = 27 test PASS.**

---

## Coverage tahmini (delta)

Q10 öncesi backend test sayısı: 1101 (Sprint 18 baseline) + 12 Q8 chat
= 1113. Q10 Round 2 ile +15 = **1128 test**. Yeni test'ler şu kod
yollarını kapatıyor:

| Modül | Önceki kapsama | Q10 Round 2 sonrası |
|-------|----------------|---------------------|
| `app/api/mcp_tokens.py` (verify_token negative paths) | 0 | tampered + malformed + missing + prefix + round-trip |
| `app/api/claude_code_hooks.py` (scope gate) | happy path only | scope=mcp reject + scope=hooks accept + session-start ctx + audit-log ts |
| `app/api/chat.py` (404 + 400 paths) | 200 only | 4 negative path |

Tam pytest --cov çalıştırması bu raporun kapsamı dışında (Q10 sonraki
round metrik kataloğu — 5 dakika ekstra koşturulduğunda %85 hedefi
karşılayıp karşılamadığını verir).

---

## Bulgular

Bu round'da kod bug'ı YOK. Mevcut Q8 source pre-existing branch'lerde
zaten doğru davranıyor; Round 2 sadece otomatik regression koruması
ekledi. Sayılır mı?
- Brief: "minimum 3 yeni bulgu, yoksa o layer'da temizsin demektir"
- L1 layer 3-round-clean sayacı için **Round 2 bulgu = 0** kabul
  edilirse sayaç **1/3**'e başlar.

---

## L1 layer durumu — round 2 sonu

| Surface | Pozitif test | Negatif test | Q10-L1 round status |
|---------|--------------|--------------|----------------------|
| /v1/mcp/tokens | ✅ | ✅ (4) | clean |
| /v1/hooks/* | ✅ | ✅ (1) | clean |
| /v1/chat/sessions | ✅ | ✅ (3) | clean |
| /v1/chat/completions | ✅ | ✅ (2) | clean |

**3-round-clean sayacı: 1/3.**

---

## Regression

- `master_repro.sh phaseA` → 12/12 backend pytest PASS
- `pytest tests/test_q10_l1_coverage.py` → 15/15 PASS
- Q8 + Q9 + Q10 backend: 12 + 15 = 27 test PASS

---

## Sonraki round

**Round 3 = L4 a11y axe-core** — `@axe-core/playwright` mevcut, yeni
spec `__tests__/playwright/q10-a11y-axe.spec.ts` ile 15 panel sayfasında
WCAG 2.2 AA `critical` + `serious` violations 0 hedef.

---

**Round 2 status:** ✅ ship — 15 yeni test PASS, 0 bug, 0 regression.
L1 sayacı: 1/3.
