import type { FC } from "react";

const Contact: FC = () => (
  <section
    id="contact"
    aria-labelledby="contact-title"
    className="container mx-auto px-4 py-24"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2
        id="contact-title"
        className="text-3xl font-bold tracking-tight sm:text-4xl"
      >
        Pilot / PoC Görüşmesi
      </h2>
      <p className="mt-4 text-muted-foreground">
        Sistemi kendi ortamınızda denemek için bizimle iletişime geçin. Pilot,
        PoC veya beta partner seçenekleri arasından sizin için en uygun olanı
        birlikte belirleyelim.
      </p>
    </div>

    <div className="mx-auto mt-12 max-w-3xl grid gap-6 md:grid-cols-3">
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">PoC</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Helm chart + dokümantasyon + temel destek. Kendi sunucunuza kurun,
          deneyin, kararınızı verin.
        </p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">Pilot</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          2 hafta özel entegrasyon, sizin sistemlerinizle bağlantı, yerinde
          destek.
        </p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <h3 className="text-base font-semibold">Beta Partner</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          30 gün boyunca tam erişim, geri bildirim ortağı. Sınırlı sayıda
          partner alıyoruz.
        </p>
      </div>
    </div>

    <div className="mx-auto mt-12 max-w-xl text-center">
      <a
        href="mailto:support@automatiabcn.com"
        className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-8 text-sm font-semibold text-primary-foreground"
      >
        support@automatiabcn.com
      </a>
      <p className="mt-3 text-xs text-muted-foreground">
        24 saat içinde dönüş yapıyoruz.
      </p>
    </div>
  </section>
);

export default Contact;
