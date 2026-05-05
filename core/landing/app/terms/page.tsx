import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kullanım Koşulları",
  description:
    "Automatia ABS self-host orchestrator için kullanım koşulları. Lisans, ödeme, sorumluluk, fesih.",
};

export default function TermsPage() {
  return (
    <main className="container mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        Kullanım Koşulları
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Son güncelleme: 27 Nisan 2026.
      </p>

      <div className="prose prose-neutral mt-8 space-y-6 text-sm leading-relaxed">
        <section>
          <h2 className="text-lg font-semibold">1. Taraflar</h2>
          <p>
            Bu sözleşme, <strong>Automatia BCN</strong> (Barcelona, İspanya — bundan sonra
            “Sağlayıcı”) ile Automatia ABS lisansını satın alan veya kullanan
            müşteri (“Kullanıcı”) arasında akdedilir. Hizmeti kullanmak için
            18 yaşından büyük olmanız gerekir.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">2. Lisans Kapsamı</h2>
          <p>
            Self-Host Lifetime ödemesi karşılığında Sağlayıcı, Kullanıcıya ABS
            yazılımını kendi sunucularında çalıştırma hakkı tanır.
            Lisans <strong>kişiseldir / kuruma özeldir</strong>; üçüncü taraflara
            devredilemez veya yeniden satılamaz. Team paketleri seat sayısına
            bağlı eşzamanlı kullanım sınırı taşır.
          </p>
          <p>
            Açık kaynak çekirdek (Apache 2.0) için ek ticari kısıtlama yoktur;
            kapalı premium add-on'lar (advanced RAG, team panel) lisans şartlarına
            tâbidir.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">3. Ödeme ve Faturalama</h2>
          <p>
            Tüm ödemeler Stripe Payments Europe Ltd. üzerinden işlenir.
            Faturalandırma KDV dahil olmayan tutarlardır; AB içi B2B alımlarda
            VIES ile doğrulama sonrası reverse charge uygulanabilir. Faturalar
            ödeme onayı sonrası 7 gün içinde email ile gönderilir.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">4. İade Politikası</h2>
          <p>
            Satın alma tarihinden itibaren <strong>14 gün içinde</strong>
            koşulsuz iade hakkı vardır. İade edilen lisansın anahtarı{" "}
            <code>revoked_at</code> olarak işaretlenir ve devre dışı bırakılır.
            Detay için <a href="/refund" className="underline">İade Politikası</a> sayfasına bakın.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">5. Yasak Kullanımlar</h2>
          <ul className="list-disc pl-6">
            <li>Yazılımı tersine mühendislik yaparak premium add-on'ları çıkarmak.</li>
            <li>Lisans anahtarını birden fazla kuruluşa dağıtmak.</li>
            <li>
              ABS aracılığıyla yasa dışı içerik üretmek veya bilgi güvenliği
              ihlali yapmak.
            </li>
            <li>Stripe'a sahte chargeback başlatmak.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold">6. Hizmet Seviyesi (SLA)</h2>
          <p>
            Self-Host kurulumlarında uptime sorumluluğu Kullanıcıya aittir.
            Maintenance paketinde Sağlayıcı, kritik güvenlik yamalarını 7 gün
            içinde duyurur ve email desteğine 48 saat içinde yanıt verir.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">7. Sorumluluğun Sınırlandırılması</h2>
          <p>
            Sağlayıcı, dolaylı zararlardan (kâr kaybı, veri kaybı, iş kesintisi)
            sorumlu değildir. Toplam sorumluluk, son 12 ayda ödenen tutarla
            sınırlıdır. Bu sınır kasıt veya ağır ihmal hâlinde uygulanmaz.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">8. Üçüncü Taraf API'lar</h2>
          <p>
            ABS, Anthropic Claude API, Groq, Cerebras, Google Gemini,
            Cloudflare Workers AI ve Cohere API'larına bağlanır. Bu sağlayıcıların
            kendi kullanım şartları geçerlidir; API anahtarlarınızı korumak
            sizin sorumluluğunuzdadır.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">9. Fesih</h2>
          <p>
            Kullanıcı, herhangi bir zamanda hizmeti kullanmayı bırakabilir.
            Sağlayıcı, sözleşmenin maddi ihlalinde 14 gün ihtarla lisansı
            sonlandırma hakkını saklı tutar.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">10. Uygulanacak Hukuk</h2>
          <p>
            Bu sözleşme İspanya Krallığı kanunlarına tâbidir. Anlaşmazlıklar,
            zorunlu tüketici hukuku saklı kalmak kaydıyla, Barcelona
            mahkemelerinde çözülür.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">11. Güncellemeler</h2>
          <p>
            Sağlayıcı, bu koşulları güncelleme hakkını saklı tutar. Önemli
            değişiklikler kayıtlı email ile 30 gün önceden duyurulur.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold">12. İletişim</h2>
          <p>
            Sözleşmeyle ilgili sorular için{" "}
            <a href="mailto:legal@automatiabcn.com" className="underline">
              legal@automatiabcn.com
            </a>
            .
          </p>
        </section>
      </div>
    </main>
  );
}
