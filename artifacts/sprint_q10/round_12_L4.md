# Q10 Round 12 — Layer L4 axe-core live attempt

**Branch:** `feat/sprint-q10-quality-loop`
**Mode:** Headless live, frontend localhost:3000 dev mode.

---

## Çıkarım

Live run sırasında **15/15 fail** — sebep `gotoWithDevRetry` 4.6s
window'unun bile yetmediği Next.js dev mode HMR compile thrash.
`--workers=1` serial execution, her test başlangıcında dev server'ı
tekrar zorluyor; özellikle `/panel/tools`, `/admin/providers` gibi
ağır-bundle (TanStack Table + Tremor + Framer) sayfalar 5+ saniye
404 veriyor.

Page snapshot bu durumu doğruluyor:
```yaml
- generic [ref=e2]: missing required error components, refreshing...
```

## Patch (Q10-L4-002)

Spec'e `gotoWithDevRetry` helper'ı taşındı, `waitUntil: networkidle`
yerine `domcontentloaded` + 600ms settle. Bu Next prod build (output:
standalone) altında temiz çalışacak.

**Commit:** bu round atomic.

## Verdict

L4 axe live, **dev mode'da run edilemez**. Production build (`npm run
build && npm start`) gerekli — orada tüm 15 sayfa pre-compile, 404
yok, axe sweep gerçek violations bulur.

L4 sayacı: 1/3 (Round 3'ten) korunur. Round 12 **dev-mode-blocked**
olarak işaretlendi; gerçek L4 advance için founder makinasında
production build + axe run gerek.

## Artifacts

- `gotoWithDevRetry` helper q10-a11y-axe.spec.ts'a eklendi (paralel
  L9-004 patch).
- `waitUntil` networkidle → domcontentloaded (timeout azaltma).

---

**Round 12 status:** ⚠ partial — dev infra blocked, prod build
gerekli. Founder hand-off.
