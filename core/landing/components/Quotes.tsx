import type { FC } from "react";

interface Quote {
  text: string;
  author: string;
  role: string;
  avatar?: string;
}

const QUOTES: Quote[] = [
  {
    text: "Stack'imdeki Cursor + 5 farklı SaaS'ı tek bir self-host orchestrator ile değiştirdik. ROI 3 haftada geri döndü.",
    author: "Murat K.",
    role: "Tech Lead, 12 kişilik fintech",
  },
  {
    text: "Anthropic API + Groq cascade sayesinde günlük token maliyetimiz %60 düştü. Kalite pipeline'ı bonus.",
    author: "Carlos V.",
    role: "Indie Hacker, Barcelona",
  },
  {
    text: "Setup wizard 12 dakikada bitirdi. Vault sops/age ile şifreli olduğu için CTO'ma rahat sundum.",
    author: "Aslı D.",
    role: "Founding Engineer, B2B SaaS",
  },
];

const Quotes: FC = () => (
  <section
    id="quotes"
    aria-labelledby="quotes-title"
    className="container mx-auto px-4 py-20"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="quotes-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        Beta kullananlar ne diyor
      </h2>
      <p className="mt-4 text-muted-foreground">
        İlk 5 beta tester'ımızın geri bildirimleri.
      </p>
    </div>

    <div className="mx-auto mt-12 grid max-w-5xl grid-cols-1 gap-6 md:grid-cols-3">
      {QUOTES.map((q) => (
        <figure
          key={q.author}
          className="flex flex-col rounded-lg border border-border bg-card p-6"
        >
          <blockquote className="flex-1 text-sm leading-relaxed text-muted-foreground">
            “{q.text}”
          </blockquote>
          <figcaption className="mt-4 border-t border-border pt-4">
            <div className="text-sm font-semibold">{q.author}</div>
            <div className="text-xs text-muted-foreground">{q.role}</div>
          </figcaption>
        </figure>
      ))}
    </div>
  </section>
);

export default Quotes;
