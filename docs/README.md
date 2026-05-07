# ABS Server Product — Docs

Bu klasör ABS'nin **ürünleştirme** çalışmasıdır. Burası **kod** değil — kod gelmeden önceki **karar** ve **araştırma** aşamasıdır.

## Neden ayrı klasör

`Automatia BCN/SERVER/` = orchestrator üretim sistemi, dokunulmaz.
`abs-server-product/` = Ürün (yeni, temiz-oda inşa).

Ürün SERVER'ın kopyası değil — aynı **özellikleri** veren, müşteri sunucusunda çalışan **yeniden yazılmış** sürüm olacak.

## Klasör yapısı

```
abs-server-product/
├── docs/                   # ← ŞU AN: karar + araştırma
│   ├── README.md           # bu dosya
│   ├── vision.md           # tek sayfada ürün vizyonu
│   ├── design-decisions.md # karara varılmış konular
│   ├── open-questions.md   # cevap bekleyen kritik sorular
│   └── research/           # gemini_search pazar araştırma özetleri
├── core/                   # (sonra) temiz-oda implementation
├── infra/                  # (sonra) docker-compose, caddy, systemd
├── marketing/              # (sonra) landing, demo, pricing page
└── business/               # (sonra) legal, contract, pricing
```

## Şu anki aşama

**Tartışma + karar.** Henüz kod yok. Kullanıcı ile 7 açık kritik soru cevaplanana kadar `core/`, `infra/` vb. boş kalır.

## Kaynak memory dosyaları

- `~/.claude/projects/.../memory/decision_20260423_product_discussion.md` — ilk tartışmanın tam özeti
- `~/.claude/projects/.../memory/vision_2026_innovation_roadmap.md` — Apr 20 vizyon roadmap
- `~/.claude/projects/.../memory/session_20260423_full_day.md` — SERVER'ın mevcut durumu (referans)

## Ne zaman kod yazılır

Şu 4 karar netleştiğinde `core/` açılır:
1. Anthropic TOS legal durumu
2. Ürün adı final
3. Lisans + revenue model (Apache 2.0 open-core + subscription öneri)
4. İlk müşteri go-to-market yolu

Aksi halde yanlış yöne kod üretme riski var.
