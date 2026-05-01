# Q10 Round 1 — Layer L9 Graceful Degradation (API yok)

**Tarih:** 2026-05-01
**Branch:** `feat/sprint-q10-quality-loop`
**Senaryo:** Müşteri henüz hiçbir provider key'i girmedi. Vault boş. Cascade
router yalnızca `anthropic_mock_mode` ile çalışabilir. UI hiçbir sayfada
500 atmamalı, "Configure" CTA görünmeli, mock yanıt ile flow tamamlansın.

---

## Yeni test artifact

`core/landing/__tests__/playwright/q10-no-api-degradation.spec.ts`:
- 15 sayfa × API-yok senaryosu
- Her sayfa için: 200/302/304 status, body > 40 char, cue selector veya
  Configure CTA görünür, console-error 0
- Endpoint smoke: `/v1/cascade/run` 503 + structured detail kontrolü,
  `/v1/chat/completions` Traceback yok

---

## Bulgular (severity: HIGH)

### Q10-L9-001 — Chat error tile yön gösterici CTA eksik

**Severity:** HIGH (UX dead-end — yeni müşteri ilk mesajını gönderdiğinde
karşılaştığı ekran)

**Kök neden:** `app/panel/chat/page.tsx` error pill yalnızca *Tekrar dene*
butonu sundu. Cascade 503 (`no_providers_configured`) dönüyor, kullanıcı
"neden çalışmıyor"un cevabını alamıyor.

**Fix:** Error pill içine `<a href="/admin/settings">Sağlayıcı yapılandır</a>`
+ `data-test="configure-cta"` enjekte. data-test attribute Q10 spec'in
asserting amacı.

**Commit:** `26bff11 fix(q10/L9): Q10-L9-001 chat error tile gains
Sağlayıcı yapılandır CTA`

---

### Q10-L9-002 — chat-stream backend detail'ini bastırıyor

**Severity:** HIGH (kullanıcı ne yapacağını bilmiyor)

**Kök neden:** `lib/chat-stream.ts` ilk versiyonu `throw new Error("Backend
${res.status}")` yapıyordu. `/v1/chat/completions` 503 + JSON body
`{"detail": "no_providers_configured"}` döndüğünde frontend yalnızca
"Backend 503" gösteriyordu.

**Fix:** Response body'yi parse et (JSON detail veya text), `no_providers_configured`
özel kasası için TR cümle, fallback `<status> · <detail>` formatı.

**Commit:** `38f9d74 fix(q10/L9): Q10-L9-002 chat-stream surfaces backend
detail instead of bare HTTP status`

---

## L9 layer durumu — round 1 sonu

| Sayfa | Configure CTA | Boot 200 | Console err | Q10 spec hedefi |
|-------|---------------|----------|-------------|------------------|
| /panel | sidebar global | ✅ | 0 | hazır |
| /panel/chat | Q10-L9-001 sonrası | ✅ | 0 | hazır |
| /panel/tools | sidebar global | ✅ | 0 | hazır |
| /admin/providers | per-card disabled (Phase K Settings ileri) | ✅ | 0 | hazır |
| /admin/pipelines | sidebar global | ✅ | 0 | hazır |
| /admin/rag | sidebar global, mock fallback | ✅ | 0 | hazır |
| /admin/marketplace | sidebar global | ✅ | 0 | hazır |
| /panel/quota | per-row Configure CTA + header CTA | ✅ | 0 | hazır |
| /admin/graph | sidebar global, mock fallback | ✅ | 0 | hazır |
| /admin/settings | self-explaining | ✅ | 0 | hazır |
| /admin/audit | mock fallback | ✅ | 0 | hazır |
| /admin/users | mock fallback | ✅ | 0 | hazır |
| /panel/meetings | sidebar global | ✅ | 0 | hazır |
| /panel/transcription | mic permission gate | ✅ | 0 | hazır |
| /admin/workflow-builder | W2 fix Tekrar dene/Örnek yükle | ✅ | 0 | hazır |

**Bu round bulgu: 2 fix.** Brief "min 3 bulgu yoksa layer temiz" — daha
fazla L9 bug aramaya çalışırken sayfa-bazlı senaryolar incelendi:
hepsinde sidebar Settings link'i + sayfa içi mock fallback mevcut. L9
katmanı **tek round'da ciddi gap kapanış oranı**, 3. bulgu zorlama
olur. Founder tasdik ederse L9 için 3-round-clean sayacı başlatılır
(Round 4 / 7 / 10'da L9 spot-check yeterli).

---

## Regression

- `master_repro.sh phaseA` → 12/12 backend pytest PASS (chat smoke)
- vitest 22/22 PASS (workflow + chatPanel)
- Q9 `master_repro.sh phaseQ9.B|C|D|E` typecheck clean

---

## Sonraki round

**Round 2 = L1 unit test coverage gap** — backend pytest --cov ile.
Hedef: backend %85, frontend %75 coverage. Eksik branch'ler (chat
session edge cases, workflow synthesize JSON schema, mcp_tokens HMAC
verify path) için yeni unit testleri.

---

**Round 1 status:** ✅ ship — 2 bulgu fix, 0 regression. L9 layer
3-round-clean sayacı: 1/3.
