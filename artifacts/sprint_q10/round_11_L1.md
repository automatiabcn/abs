# Q10 Round 11 — Layer L1 re-scan (regression + coverage spot-audit)

**Branch:** `feat/sprint-q10-quality-loop`

---

## Komutlar

```bash
cd core/backend
.venv/bin/python -m pytest \
  tests/test_q10_l1_coverage.py \
  tests/test_q10_l2_integration.py \
  tests/test_q8_chat.py -q --no-header
```

## Sonuç

```
.....................................                          [100%]
37 passed, 1 warning in 13.57s
```

Toplam **37 test PASS**:
- `test_q8_chat.py` — 12 (Q8 Phase A chat baseline)
- `test_q10_l1_coverage.py` — 18 (5 mcp HMAC + 7 hooks scope + 6 chat 404)
- `test_q10_l2_integration.py` — 7 (cascade + tools + providers + lifecycle)

---

## Bulgular

**0 yeni bulgu.** Mevcut Q10 L1 + L2 + Q8 chat suite Q9 + Q10 sonrası
hâlâ stabil. Round 5 Q10-L6-001 quota-check fix'i de regression-safe
(L6'da eklenen 3 test yine L1 dosyasında PASS).

---

## L1 layer durumu — Round 11 sonu

L1 sayacı:
- Round 2: 0 yeni bug, 15 test ekleme → 1/3
- Round 11: 0 yeni bug → **2/3**

**FULL CLEAN için 1 round daha** L1'de 0 yeni bulgu lazım (Round ~20+ rotation).

---

## Coverage spot-audit

Q10 L1 testleri kapsadığı kod yolları:
- `mcp_tokens.verify_token` happy + 4 negative path (sign/prefix/sig/malformed)
- `claude_code_hooks.quota_check` allow + deny + non-risky
- `claude_code_hooks._auth_from_header` scope=mcp reject, hooks accept, all accept
- `chat.completions` empty messages + non-user-last 400 path
- `chat.list_messages` cross-tenant 404
- `chat.delete_session` 404
- `chat.rename_session` 404

Ölçülmüş cov yüzdesi pytest-cov olmadığı için tahmini — Round ~14+
L1 rotation'ında cov-driven measurement eklenebilir.

---

## Regression baseline

37 backend pytest + 22 vitest + Q9 master_repro phaseA = baseline
intact since Q10 Round 1.

---

## Sonraki round

**Round 12 = L4 a11y axe live** — `q10-a11y-axe.spec.ts` headless
çalıştır + bulgu üret + fix.

---

**Round 11 status:** ✅ ship — 0 bug, regression-safe. L1 sayacı: 2/3.
