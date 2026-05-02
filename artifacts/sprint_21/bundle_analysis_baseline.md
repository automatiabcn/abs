# Sprint 21 — Faz A Bundle Analysis Baseline

**Tarih:** 2026-05-02
**Branch:** `feat/sprint-21-perf-architecture`
**Build:** `ANALYZE=true npm run build` (Next 15.5.15, output:standalone)

Snapshot of `webpack-bundle-analyzer` client report saved at
`bundle_analyzer_client_baseline.html` (924 KB, opens in browser).

---

## Per-route bundle (uncompressed)

From `.next/app-build-manifest.json` × file sizes on disk:

| Route | Self KB | First-Load KB | Total all chunks |
|-------|--------:|--------------:|-----------------:|
| /panel | 113 | 273 | **924K** |
| /panel/chat | 103 | 261 | 854K |
| /panel/quota | 67.5 | 222 | 711K |
| /panel/tools | 19.6 | 189 | 613K |
| /admin/workflow-builder | 70.4 | 180 | 582K |
| /admin/marketplace | 10.9 | 160 | (smaller) |
| /admin/providers | 8.05 | 166 | (smaller) |
| /panel/transcription | 5.94 | 127 | (smaller) |
| /panel/meetings | 6.01 | 115 | (smaller) |

**Worst LCP-blocking routes per Q11-L5-001:**
- `/panel/chat` — LCP 9.9s (slow 3G + CPU 4×)
- `/panel/tools` — LCP 8.6s

---

## Top 12 chunks by raw size

| Size | Chunk | Likely contents |
|-----:|-------|-----------------|
| 548K | `0c85d44c.9e70607ddf42449e.js` | **three** — react-force-graph (NeuralGraph) |
| 404K | `9150-c8757b5467b7873a.js` | **recharts + tremor** — Tremor chart family |
| 376K | `bd904a5c.352d49427cddcfba.js` | (minified, ~Tremor/framer subset) |
| 352K | `b536a0f1.5bb832777e6ae378.js` | **three** variant |
| 340K | `9d78c252.d9c3b2141ac84ec9.js` | **three** variant |
| 324K | `397-ce7a1ceb3e07c68d.js` | **react-markdown** + remark stack (chat) |
| 316K | `63d2ba32.08e837edee3b8024.js` | (minified) |
| 240K | `3529.127156e528e93f3c.js` | **three** variant |
| 200K | `9938-f5da005089cabb67.js` | **tremor** |
| 188K | `framework-fc89765f6eabdf02.js` | React 19 framework (unavoidable) |
| 172K | `1255-55f5611cfd370a3f.js` | Next.js internals (shared, unavoidable) |
| 172K | `4bd1b696-100b9d70ed4e49c1.js` | React (shared, unavoidable) |

---

## Top 5 fix targets (sequencing for Faz B → F)

| # | Target | Cost | Tactic | Faz |
|---|--------|-----:|--------|-----|
| 1 | **Tremor + Recharts** | ~600K (9150 + 9938 + bd9) | `next/dynamic({ssr:false})` for QuotaBars / ProvidersSparkline / AuditTimeline | B |
| 2 | **Chat SSE + react-markdown + AI SDK** | ~324K (397) + chat surface | `dynamic` import the chat client component; lazy-load `cmdk` slash palette on `/` keystroke | C |
| 3 | **NeuralGraph (three.js)** | ~1.5MB across 3 chunks (0c85 + 9d78 + b536 + 3529) | Already `dynamic` per src — verify the bundle still ships them lazy + skip on `prefers-reduced-motion` | D |
| 4 | **Lucide-react** | unknown without sourcemap; per-icon import audit | Switch to `lucide-react/dist/esm/icons/<name>` for hot-path imports; baseline + measure | E |
| 5 | **Fonts (next/font/google)** | inferred; need network tab measure | Verify `subsets: ["latin","latin-ext"]` + `display:swap` + weight prune | F |

---

## Unavoidable baseline (after Faz B-F)

The React + Next runtime chunks (framework + 1255 + 4bd1 + main-app) sum
to ≈530K uncompressed. With brotli/gzip at the edge that's ~150K
on-the-wire. This is the floor for any panel route's first-load.

Therefore the realistic budget after Faz B-F:
- Panel chrome (sidebar + header + theme provider) ≤ **200K gzipped**
  (≤ ~600K uncompressed including framework)
- Per-page payload (chat / tools / quota / workflow): ≤ **150K gzipped
  on top of chrome**
- LCP target ≤ 2.5s on slow 3G + CPU 4× (Q11-L5-001 budget)

---

## Verification harness for Faz H

`artifacts/sprint_21/master_repro.sh` will:
1. `ANALYZE=true npm run build` → diff client.html vs baseline
2. Lighthouse CPU 4× / slow 3G on 5 surfaces
3. Q10 + Q11 spec regression sweep
4. Backend pytest 88-test sweep

If any of those fail, the faz commit is reverted.
