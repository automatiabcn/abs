# Sprint 21 — Faz G image optimize audit

**Tarih:** 2026-05-02

## Bulgu

`core/landing/public/` directory **boş** (0 raster image).

```bash
$ ls -lh public/
total 0
$ find . -name '*.png' -not -path './node_modules*' -not -path './.next*' \
    -not -path '*playwright*'
(no matches)
```

`grep -rn 'next/image' app components` — `next/image` kullanımı yok.

Tüm görsel öğeler:
- Inline SVG (`AbsLogo` sidebar/header'da)
- Lucide-react SVG icon'lar
- CSS oklch token'ları (border + background)
- Brand mark — inline `<svg>` (Header.tsx + AbsLogo)

## Brief'te bahsedilen `og.png`

Yok. `app/layout.tsx` metadata'da `og:image` referansı şu şekilde:

```
"og:image", "https://abs.automatiabcn.com/og.png"
```

Production deploy'da Caddy/CDN'den serve edilecek — bu repo'da
shipped değil.

## Karar

`Faz G refactor SKIP`. Image payload halihazırda **0 KB** (kullanıcının
ilk render'ında raster image yok). LCP candidate'ı text/SVG olduğu
için image optimization gerekmiyor.

## Aksiyon

Faz H — verification + Lighthouse re-baseline'a geç.
