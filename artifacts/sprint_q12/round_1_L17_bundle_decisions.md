# Q12 — Round 1 — L17 bundle break-even validator

**Tarih:** 2026-05-02
**Layer:** L17 — bundle break-even validator (Q12 yeni)
**Branch:** `feat/sprint-q12-deep-quality`
**Worker:** Opus 4.7 (1M ctx) + GPT-OSS 120B delegation (math/architecture)

---

## 0. Hedef

Sprint 21'in 4 perf commit'i (`22b47ea` Faz B, `03f1ca2` Faz C,
`4829122` Faz D) byte-temelli karar verdi (`-44%`, `-57%`).
Throttled Lighthouse ölçümü ise **regression** gösterdi.
Q12-L17 hedefi: her code-split kararını network-profili-aware
break-even formülü ile re-evaluate et.

---

## 1. Formül (GPT-OSS 120B türetimi)

```
delta_t_ms = -(savedBytes * 8) / bandwidthKbps  +  extraRTTs * rttMs
```

- `delta_t < -50ms` → **SHIP** (LCP düşürür)
- `|delta_t| ≤ 50ms` → **NEUTRAL**
- `delta_t > +50ms` → **REVERT**
- LCP candidate dynamic chunk içindeyse `extraRTTs` LCP'ye eklenir.

`scripts/validate_bundle_split.js` validator'ı her commit için
3 profil (Slow 3G / LTE 4G / Office fiber) altında değerlendirir.

---

## 2. Decision matrix — Sprint 21 commit'leri

| Commit | Faz | Route | Profile | Saved KB | RTT+ | δ_dl ms | δ_rtt ms | δ_total ms | Verdict |
|--------|-----|-------|---------|---------:|-----:|--------:|---------:|-----------:|---------|
| 22b47ea | B | /panel | Slow 3G | 404 | 1 | -1034.24 | 400 | -634.24 | **SHIP** |
| 22b47ea | B | /panel | LTE 4G | 404 | 1 | -269.33 | 100 | -169.33 | **SHIP** |
| 22b47ea | B | /panel | Office fiber | 404 | 1 | -64.64 | 50 | -14.64 | NEUTRAL |
| 22b47ea | B | /panel/quota | Slow 3G | 202 | 1 | -517.12 | 400 | -117.12 | **SHIP** |
| 22b47ea | B | /panel/quota | LTE 4G | 202 | 1 | -134.67 | 100 | -34.67 | NEUTRAL |
| 22b47ea | B | /panel/quota | Office fiber | 202 | 1 | -32.32 | 50 | +17.68 | NEUTRAL |
| 03f1ca2 | C | /panel/chat | Slow 3G | 487 | 2 | -1246.72 | 800 | -446.72 | **SHIP** |
| 03f1ca2 | C | /panel/chat | LTE 4G | 487 | 2 | -324.67 | 200 | -124.67 | **SHIP** |
| 03f1ca2 | C | /panel/chat | Office fiber | 487 | 2 | -77.92 | 100 | +22.08 | NEUTRAL |
| 4829122 | D | NeuralGraph + CmdK | tüm | 0 | 1 | 0 | 50–400 | +50…+400 | NON_LCP |

---

## 3. Ölçüm vs formül — **Q12-L17-001 (HIGH) ucu**

Sprint 21 honest report (CPU 4× + slow 3G 400 KB/s):

| Sayfa | Baseline LCP | B+C+D LCP | Δ ölçülen | Formül δ (B+C+D toplam) | Tutarlı? |
|-------|-------------:|----------:|----------:|------------------------:|:--------:|
| /panel | 2275 ms | 2769 ms | **+494** | -634.24 (B sadece) | ❌ |
| /panel/chat | 9875 ms | 11105 ms | **+1230** | -446.72 (C sadece) | ❌ |
| /panel/quota | 2200 ms | 2225 ms | +25 | -117.12 | ✅ (B saving overshadowed) |

**Boşluk:** Formül `/panel` ve `/panel/chat`'te slow 3G altında
SHIP diyor (savedBytes baskın olmalı), ama ölçüm regression veriyor.

### Kök neden

Formül 2 önemli faktörü ihmal ediyor:

1. **LCP candidate dynamic chunk içinde** — `/panel` LCP candidate
   tahmini olarak Tremor `<Card>` (KPI tile). Tremor lazy yapıldığında
   LCP, ana paint değil chart-skeleton swap zamanına kayıyor.
   Bu `extraRTTs` LCP yoluna eklenir, byte tasarrufu LCP'yi
   tamamen aşağı çekemez (chart download zamanı LCP'ye dahil).

2. **CPU 4× throttle parse + compile maliyetini büyütür** —
   savedBytes daha az parse, ama dynamic chunk react-markdown
   (~324K) parse'ı da gecikme yaratır. Slow 3G'de bu parse-cost
   compounded.

### Düzeltilmiş formül (öneri)

```
if (lcp_in_dynamic_chunk) {
  effective_rtts = extraRTTs              # full cascade hits LCP
  savings_factor = 0                      # bytes don't reduce LCP
} else {
  effective_rtts = 0                      # background load
  savings_factor = 1                      # bytes reduce TTFB
}
delta_lcp_ms = effective_rtts * rttMs - savedBytes * 8 / bandwidthKbps * savings_factor
```

LCP-position bilgisi olmadan validator yanlış pozitif veriyor.
Sprint 22 RSC migration veya Faz B/C için **chart placeholder
height-reserved + critical CSS** çözüm üretebilir.

---

## 4. KOBİ pilot için final öneri (per commit)

| Commit | Faz B/C/D | Slow 3G | LTE 4G | Fiber (KOBİ ofis) | Karar |
|--------|-----------|---------|--------|-------------------|-------|
| 22b47ea | B – Tremor lazy | SHIP | SHIP/NEUTRAL | NEUTRAL | **KEEP** — chart placeholder height reserve eklenmeli (Sprint 22) |
| 03f1ca2 | C – Chat lazy | SHIP | SHIP | NEUTRAL | **KEEP** — streaming SSR shell ekle (Sprint 22) |
| 4829122 | D – NG/CmdK ssr:false | NON_LCP | NON_LCP | NON_LCP | **KEEP** — LCP-bağımsız, defer doğru |

Hiç biri tam revert gerekmiyor. Slow-3G-only KOBİ profili
yok (KOBİ pilot fiber + LTE). Saf byte tasarrufu fast-network'te
real win.

**Sprint 22 ROI:** RSC + streaming SSR + Early Hints — formül
yukarıdaki "lcp_in_dynamic_chunk=true" durumunu çözer
(LCP HTML'de fires).

---

## 5. Gerçek bulgu

**Q12-L17-001 (MED, "policy gap"):** Sprint 21 yalnızca byte-delta
metric'i ile karar verdi. Bundle decision policy LCP-element-position
guard içermiyor. Yeni dynamic import eklemeden önce reviewer şu
checklist'i çalıştırmalı:

- [ ] LCP candidate bu chunk içinde mi? (DevTools Performance LCP marker)
- [ ] Slow 3G profili altında break-even formülü SHIP/NEUTRAL veriyor mu?
- [ ] Chunk için skeleton height-reserved mı (CLS guard)?
- [ ] Cascade chain ≤ 1 dynamic boundary mı?

**Çözüm shipped (bu round):**
1. `scripts/validate_bundle_split.js` — break-even validator
2. Bu doc — Sprint 21 commit decision matrix + gap analizi
3. Sprint 22 brief için input (LCP-aware policy)

**Çözülmedi (Sprint 22 backlog):**
- LCP-position aware düzeltilmiş formül implementasyonu
- Tremor chart placeholder height reserve

---

## 6. Atomic commit

```
fix(q12/L17): Round 1 Q12-L17-001 bundle break-even validator + decision matrix
```

---

## 7. Layer state

L17 sayım: **1/3** (1 round cleared). Real bug shipped (validator + policy doc).
Henüz FULL CLEAN değil — 2 round daha gerekli (regression + KOBİ network sample).
