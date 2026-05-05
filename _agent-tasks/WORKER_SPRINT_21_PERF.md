# Sprint 21 — Perf Architecture (Mobile + Throttled Network Budget)

> **Tetikleyici:** Q11-L5-001 backlog. Chat LCP 9.9s + Tools LCP 8.6s under CPU 4× / slow 3G. Core Web Vitals budget 2.5s. KOBİ pilot müşterisi eski laptop + zayıf wifi'da 10 saniye beyaz ekran görür → bounce.
> **Hedef:** Chat + Tools LCP ≤2.5s slow 3G + CPU 4× throttle. Q10/Q11 hiçbir test'i kırma.
> **Branch:** `feat/sprint-21-perf-architecture` (Q11 FULL CLEAN sonrası)
> **Worker:** Opus 4.7 (1M context) + %70+ MCP delegation

---

## 0. Ön Koşullar

```bash
git checkout feat/sprint-q11-deep-sweep && git pull
git checkout -b feat/sprint-21-perf-architecture
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml ps  # backend healthy
cd core/landing && npm run build  # baseline bundle size
```

**Baseline metrikleri (slow 3G + CPU 4× throttle):**
- Chat LCP: 9.9s (target ≤2.5s, **gap -7.4s**)
- Tools LCP: 8.6s (target ≤2.5s, **gap -6.1s**)
- Panel main LCP: ?  (ölç + raporla)
- Workflow-builder LCP: ? (react-flow heavy)
- Bundle size: ? KB initial JS, ? KB lazy

**Budget (Core Web Vitals + ekstra):**
- LCP ≤2.5s (slow 3G + CPU 4×)
- INP ≤200ms
- CLS ≤0.1
- TBT ≤300ms
- FCP ≤1.8s
- Initial JS bundle ≤200KB gzipped (panel chrome)

---

## 1. Faz Sıralaması

```
Faz A → B → C → D → E → F → G (sequential, atomic commit per faz)
```

---

## 2. Faz A — Bundle Analiz (1h)

```bash
cd core/landing
ANALYZE=true npm run build
# webpack-bundle-analyzer otomatik açılır
# Top 20 modules raporla:
# - react-flow (xyflow): bundle size?
# - tremor: bundle size?
# - vercel ai-sdk: bundle size?
# - cmdk: bundle size?
# - react-force-graph-3d: bundle size?
# - lucide-react: tree-shaking çalışıyor mu? (per-icon import)
```

**Çıktı:** `artifacts/sprint_21/bundle_analysis_baseline.md` — top 20 modül + çözüm önceliği.

**Hedef:** Bundle dump'ında en büyük 5 modülü tespit et. Genelde:
1. Tremor charts (Recharts altında, ~400KB minified)
2. react-flow (xyflow, ~250KB)
3. react-force-graph-3d (Three.js ile, ~600KB)
4. Vercel AI SDK (~150KB)
5. Lucide react (full lib import edilmişse ~500KB)

---

## 3. Faz B — Tremor + Recharts Lazy Load (2h)

**Sorun:** Tremor BarList, ProgressBar, DateRangePicker → her panel sayfasında initial bundle'a giriyor. Recharts altta yatıyor (~400KB).

**Çözüm:**
- `next/dynamic` + `{ ssr: false }` ile chart komponentlerini lazy:
```tsx
import dynamic from "next/dynamic";

const QuotaProgressBar = dynamic(
  () => import("@/components/panel/QuotaProgressBar").then(m => m.QuotaProgressBar),
  { ssr: false, loading: () => <Skeleton className="h-2 w-full" /> }
);
```

**Sayfalar:** /panel (Tool kategorileri), /panel/quota (ProgressBar), /admin/providers (sparkline), /admin/pipelines (race ratio), /admin/audit (timeline).

**Doğrulama:** Bundle analyzer re-run → Tremor/Recharts lazy chunk'a geçti mi? Initial bundle ≤200KB?

**Atomic commit:** `perf(s21/B): tremor + recharts lazy load via next/dynamic`

---

## 4. Faz C — Chat SSE Code-Split (2h)

**Sorun:** `lib/chat-stream.ts` + Vercel AI SDK chat sayfası açılırken initial bundle'a giriyor. Diğer 14 sayfada gereksiz.

**Çözüm:**
- `app/panel/chat/page.tsx` → `dynamic(() => import("@/components/chat"), { ssr: false })`
- Suspense boundary + skeleton chat bubble
- Slash command palette (cmdk) → user `/` tuşuna basınca lazy import

**Doğrulama:** Network tab → chat sayfası girene kadar `chat-stream.js` chunk'ı çekilmiyor olmalı.

**Atomic commit:** `perf(s21/C): chat sse + slash palette code-split`

---

## 5. Faz D — Defer Non-Critical JS (1.5h)

**Sorun:** cmdk command palette + react-force-graph-3d (sistem haritası) initial bundle'da, ama kullanıcı genelde 5-10sn sonra kullanıyor.

**Çözüm:**
- **Cmdk palette:** `useEffect(() => { import("./CommandPalette"); }, [])` deferred load (idle callback)
- **Neural graph:** `dynamic(() => import("@/components/panel/NeuralGraph"), { ssr: false, loading: <NeuralGraphSkeleton /> })` (zaten dynamic ama bundle path doğrula)
- **Three.js full:** lazy + Canvas placeholder

**Doğrulama:** Lighthouse → Total Blocking Time (TBT) ≤300ms.

**Atomic commit:** `perf(s21/D): cmdk + neural graph deferred load`

---

## 6. Faz E — Lucide Icon Tree-Shake (30dk)

**Sorun:** `import { Mic, Upload } from "lucide-react"` → tüm Lucide kütüphanesi bundle'a giriyor (500KB+).

**Çözüm:** `lucide-react/icons/*` per-icon import'a geç:
```tsx
import Mic from "lucide-react/dist/esm/icons/mic";
import Upload from "lucide-react/dist/esm/icons/upload";
```
Veya babel-plugin-lucide ile auto-transform.

**Doğrulama:** Bundle analyzer → lucide-react chunk size ≤30KB.

**Atomic commit:** `perf(s21/E): lucide-react per-icon import (tree-shake)`

---

## 7. Faz F — Font Subset + Display Swap (30dk)

**Sorun:** Inter + JetBrains Mono full Latin-Ext + Vietnamese + Greek = 200KB+ font payload. Türkçe + İngilizce + İspanyolca için Latin yeterli.

**Çözüm:** `next/font/google` ile subset zaten Latin-set ediliyor mu doğrula. Display swap aktif mi?

```tsx
const inter = Inter({
  subsets: ["latin", "latin-ext"],  // TR için latin-ext gerek
  display: "swap",  // ZORUNLU — fallback font ile FCP korur
  preload: true,
  weight: ["400", "500", "600", "700"],  // 100/200/300/800/900 kaldır
  variable: "--font-display",
});
```

**Doğrulama:** Network tab → font payload ≤80KB toplam, FCP'yi blocklamayan.

**Atomic commit:** `perf(s21/F): font subset latin-ext + weight prune`

---

## 8. Faz G — Image Optimize + Static Asset (1h)

**Sorun:** Logo SVG inline ✓ ama başka asset?
- `/og.png` (social share, 1200×630) — sıkıştırma
- Marketplace plugin logoları — varsa Next/Image ile lazy + AVIF
- Screenshot illustration — yok ama kontrol et

**Çözüm:**
- `next/image` zaten kullanılıyor mu? Otomatik AVIF/WebP convert.
- `og.png` → tinify/squoosh ile ≤80KB
- Static asset'ler `public/` altında ise `next/image` ile lazy

**Doğrulama:** Network tab → ana sayfa ilk render'da ≤500KB toplam (font + JS + CSS + image).

**Atomic commit:** `perf(s21/G): image optimize + og.png squoosh`

---

## 9. Faz H — Verification + Re-baseline (1h)

```bash
# Build
cd core/landing && npm run build && npx next start -p 3458 &
sleep 5

# Lighthouse 3 senaryo
npx lighthouse http://localhost:3458/panel/chat \
  --preset=desktop --throttling.cpuSlowdownMultiplier=4 \
  --throttling.requestLatencyMs=400 --throttling.downloadThroughputKbps=400 \
  --throttling.uploadThroughputKbps=400 \
  --output=json --output-path=artifacts/sprint_21/lh_chat_throttled.json

# Aynı: /panel/tools, /panel, /admin/workflow-builder, /admin/providers
```

**Hedef metrik (her sayfa):**
- LCP ≤2.5s ✓
- FCP ≤1.8s ✓
- TBT ≤300ms ✓
- CLS ≤0.1 ✓
- Performance score ≥90 ✓

**Regression test:**
```bash
# Q10 + Q11 specs hala PASS olmalı
PLAYWRIGHT_BASE_URL=http://localhost:3458 npx playwright test \
  q10-no-api-degradation q10-a11y-axe q10-theme-matrix \
  q11-l11 q11-l12 q11-l13 \
  --reporter=list

# Backend regression
docker exec infra-backend-1 sh -c "cd /app && python -m pytest tests/ -q"
```

**Atomic commit:** `verify(s21/H): re-baseline lighthouse + regression PASS`

---

## 10. Çıktı

```
artifacts/sprint_21/
├── bundle_analysis_baseline.md        (Faz A)
├── bundle_analysis_post.md            (Faz H)
├── lh_chat_baseline.json              (önce)
├── lh_chat_throttled.json             (sonra)
├── lh_tools_baseline.json
├── lh_tools_throttled.json
├── lh_panel_throttled.json
├── lh_workflow_throttled.json
├── lh_providers_throttled.json
├── master_audit_summary.md            (LCP önce/sonra tablosu)
└── master_repro.sh                    (Faz A-H entry)
```

**master_audit_summary.md tablosu:**

| Sayfa | LCP önce | LCP sonra | Δ | Score önce | Score sonra |
|-------|----------|-----------|----|-----------|------------|
| /panel/chat | 9.9s | ?s | ? | ? | ? |
| /panel/tools | 8.6s | ?s | ? | ? | ? |
| /panel | ?s | ?s | ? | ? | ? |
| /admin/providers | ?s | ?s | ? | ? | ? |
| /admin/workflow-builder | ?s | ?s | ? | ? | ? |

---

## 11. Delegation

- Bundle analiz: kendin (webpack-bundle-analyzer çıktısı görsel)
- Lazy load patch'leri: `mcp__abs__ask_kimi` (next/dynamic boilerplate)
- Lucide tree-shake: `mcp__abs__ask_gptoss` (babel plugin config)
- Font subset analizi: `mcp__abs__ask_qwen32b` (TR/EN/ES karakter set)
- Code review per faz: `mcp__abs__code_review tier=standard`
- Lighthouse JSON yorumu: `mcp__abs__ask_gemini_pro`

---

## 12. Yasaklar

- **Architectural değişiklik ≠ test düşürme.** Q10/Q11 specs PASS olmadan faz commit edilmez.
- **Dynamic import unutulan kütüphane yok** — bundle analyzer önce/sonra karşılaştırılır.
- **Font swap olmadan deploy yok** — FOIT (Flash of Invisible Text) FCP'yi tahrip eder.
- **CDN cache header kontrolü** — static asset'ler `cache-control: max-age=31536000, immutable` ile gönderiliyor mu? Caddy config'inde.

---

## 13. Geçme Kriteri

| Check | Hedef |
|-------|-------|
| Chat LCP slow 3G + CPU 4× | ≤2.5s |
| Tools LCP slow 3G + CPU 4× | ≤2.5s |
| Panel main LCP slow 3G + CPU 4× | ≤2.5s |
| Workflow-builder LCP slow 3G + CPU 4× | ≤2.5s |
| Providers LCP slow 3G + CPU 4× | ≤2.5s |
| Initial JS bundle (panel chrome) | ≤200KB gzipped |
| Lighthouse perf score | ≥90 her sayfa |
| Q10 + Q11 specs regression | 0 fail |
| Backend pytest | 78/78 PASS (Q8 + Q10 + Q11) |

---

## 14. Tahmin

- Sequential: ~10 saat (Faz A-H)
- Delegation %70+ ile: ~6 saat
- Founder verify: 1 saat (Lighthouse re-run + Playwright regression)

**Total: 1 iş günü.**

---

## 15. Sonraki Sprint

Sprint 22 = real provider integration (müşteri API key girer, cascade chain gerçek call testi)
Sprint 23 = production deploy drill (Caddy + Docker prod compose + secrets vault)
