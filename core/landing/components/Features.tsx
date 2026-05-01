import type { FC } from "react";

interface Feature {
  title: string;
  description: string;
}

const FEATURES: Feature[] = [
  {
    title: "100+ MCP tool",
    description:
      "Hazır kurulu, uzatılabilir. Kendi tool'larını ekleyebilirsin (Q1 ölçüm: 122 tool).",
  },
  {
    title: "13 kalite pipeline'ı",
    description:
      "qual-code, qual-tr, qual-analysis, judge — birden fazla modeli zincirleyen üretim akışları.",
  },
  {
    title: "6 sağlayıcı cascade",
    description:
      "Anthropic, Groq, Cerebras, Gemini, CloudFlare, Cohere — biri düşerse diğeri devreye girer.",
  },
  {
    title: "Symbol-aware RAG",
    description:
      "10K+ sembol indeksi ve callsite graph — embedding tabanlı aramadan farkı burada başlıyor.",
  },
  {
    title: "Senior Judge",
    description:
      "Diff'leri AST metrikleri + LLM yargısı ile birleştirip kalite skoru üretir.",
  },
  {
    title: "Türkçe kalite pipeline'ı",
    description:
      "Çok dilli modeller için Türkçe'ye özel üret-kontrol-polish akışı.",
  },
  {
    title: "16 saniye warm-boot",
    description: "Docker Compose tek komut. Image cache'liyse cold-start 16s, ilk kurulum dakikalar içinde. SSH bilen herkes kurabilir.",
  },
  {
    title: "6 ay dogfooding",
    description:
      "Kurucu bizzat günlük kullanıyor — her özellik gerçek iş akışından çıktı.",
  },
];

const Features: FC = () => (
  <section
    id="features"
    aria-labelledby="features-title"
    className="container mx-auto px-4 py-24"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="features-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        Kutudan çıkan yetenekler
      </h2>
      <p className="mt-4 text-muted-foreground">
        Herhangi bir eklenti marketplace'ine bağlı değilsin — hepsi repoda.
      </p>
    </div>

    <ul className="mx-auto mt-16 grid max-w-5xl grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {FEATURES.map((f) => (
        <li
          key={f.title}
          className="rounded-lg border border-border bg-card p-6 text-left shadow-sm"
        >
          <h3 className="text-base font-semibold">{f.title}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{f.description}</p>
        </li>
      ))}
    </ul>
  </section>
);

export default Features;
