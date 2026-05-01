import type { FC } from "react";

interface QA {
  q: string;
  a: string;
}

const QUESTIONS: QA[] = [
  {
    q: "Anthropic TOS ihlali değil mi?",
    a: "Hayır. ABS, Anthropic'in ticari API koşulları (pay-per-use) üzerinden çalışır. Pro aboneliğine bağlı OAuth token'ı değil, doğrudan API anahtarı kullanılır; bu kullanım Anthropic tarafından açıkça desteklenir.",
  },
  {
    q: "Kurulum teknik bilgi gerektiriyor mu?",
    a: "Temel Docker bilgisi yeterli. `docker compose up -d` tek komutla dakikalar içinde ABS ayağa kalkar (warm restart 16 saniye, ilk image pull dahil ~5-10 dakika). SSH veya terminal kullanabilen bir geliştirici için sorun çıkarmaz.",
  },
  {
    q: "Lisansımı kaybedersem ne olur?",
    a: "Lisans anahtarı hem satın alma sonrası e-postanızda hem de ABS yönetim panelinde saklıdır. Kaybederseniz destekle iletişime geçerek mevcut ödemenizle tekrar alabilirsiniz.",
  },
  {
    q: "İade garantisi var mı?",
    a: "Evet. 14 gün içinde koşulsuz iade alabilirsiniz — doğrudan Stripe üzerinden, soru sormadan. İade sonrası lisans anahtarı iptal edilir.",
  },
  {
    q: "Destek nasıl çalışır?",
    a: "Temel planda e-posta desteği standarttır (support@automatiabcn.com). Bakım paketi alanlar için 48 saat yanıt SLA'sı geçerlidir.",
  },
  {
    q: "Kodum Anthropic'e veya Automatia'ya gönderiliyor mu?",
    a: "Automatia sunucusuna gelmez. ABS sizin sunucunuzda çalışır ve doğrudan sizin Anthropic API anahtarınızla konuşur. Claude API çağrılarında istek içeriği Anthropic'e gider — bu her Claude kullanımının doğal parçasıdır.",
  },
  {
    q: "Cursor / Cline / Aider varken neden ABS?",
    a: "ABS bir IDE eklentisi değil, self-host bir AI ağı. 100+ MCP tool (122 ölçüldü), 6 sağlayıcı cascade (Anthropic, Groq, Cerebras, Gemini, CloudFlare, Cohere), kalite pipeline'ları ve RAG birlikte gelir. Kurucu 6 aydır ürünü bizzat kullanarak geliştiriyor.",
  },
  {
    q: "Güncellemeler nasıl gelir?",
    a: "`docker compose pull && docker compose up -d` komutu yeterli. Self-Host Lifetime planı 1 yıl güncelleme alır; Maintenance paketi aldığınız sürece güncellemeler sürekli gelir.",
  },
  // 018 — yeni 4 soru
  {
    q: "Anthropic API anahtarımı sops/age vault nasıl koruyor?",
    a: "ABS, sops + age ile şifrelenmiş bir vault kullanır. ANTHROPIC_API_KEY, ABS_STRIPE_SECRET_KEY ve ABS_STRIPE_WEBHOOK_SECRET disk üzerinde her zaman şifreli durur; sadece backend boot sırasında bellekteki settings nesnesine açılır. Yedeği age private key dosyasıdır — onu cold storage'da saklarsınız, kaybedilirse vault sıfırdan yeniden oluşturulur.",
  },
  {
    q: "İade nasıl alınır, kaç gün geçerli?",
    a: "Satın alma tarihinden itibaren 14 gün içinde Stripe portal üzerinden tek tıkla iade alabilirsiniz. POST /v1/billing/portal endpoint'i sayfanın üstündeki Manage butonu ile açılır; email girersiniz, Stripe Customer Portal'a yönlendirilirsiniz. İade onaylanır onaylanmaz lisans anahtarı revoked_at = now ile pasif olur ve refund email gelir.",
  },
  {
    q: "GDPR ve veri ikametgâhı (data residency) nasıl ele alınıyor?",
    a: "ABS sizin sunucunuzda çalıştığı için tüm müşteri verisi sizin yargı bölgenizde kalır — Automatia BCN sunucularına hiçbir kullanıcı verisi gönderilmez. Sadece Stripe ödeme verisi (email + ödeme detayı) Stripe'ın altyapısında işlenir; bu PCI-DSS Level 1 sertifikalıdır. Kullanıcı talep ederse Stripe Dashboard'dan veri silme talebi gerçekleştirilebilir.",
  },
  {
    q: "Açık kaynak mı? Lisans modeli nedir?",
    a: "Backend ve landing açık kaynaktır (Apache 2.0). Premium add-on'lar (advanced RAG, team panel, gelecekteki SaaS modu) kapalı modüllerdir. Self-Host Lifetime satın aldığınızda hem açık çekirdeği hem premium add-on'ları ömür boyu kullanım hakkına sahip olursunuz.",
  },
];

const FAQ: FC = () => (
  <section
    id="faq"
    aria-labelledby="faq-title"
    className="container mx-auto px-4 py-24"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2 id="faq-title" className="text-3xl font-bold tracking-tight sm:text-4xl">
        Sık sorulan sorular
      </h2>
    </div>

    <ul className="mx-auto mt-12 max-w-3xl space-y-4 list-none p-0">
      {QUESTIONS.map((item) => (
        <li key={item.q}>
        <details
          className="group rounded-lg border border-border bg-card p-5"
        >
          <summary className="flex cursor-pointer items-center justify-between text-base font-medium">
            <span role="term" data-testid="faq-term">{item.q}</span>
            <span
              aria-hidden="true"
              className="ml-4 text-muted-foreground transition-transform group-open:rotate-45"
            >
              +
            </span>
          </summary>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {item.a}
          </p>
        </details>
        </li>
      ))}
    </ul>
  </section>
);

export default FAQ;
