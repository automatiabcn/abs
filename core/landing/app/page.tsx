import Demo from "@/components/Demo";
import FAQ from "@/components/FAQ";
import Features from "@/components/Features";
import Footer from "@/components/Footer";
import Hero from "@/components/Hero";
import Quotes from "@/components/Quotes";
import Contact from "@/components/Contact";

const heroTitle = "Kendi sunucunda 100+ MCP tool ve 6 sağlayıcı cascade — tek paket, kendi altyapın.";

const heroSubtitle = "Automatia ABS: Claude Pro aboneliğinle çalışan RAG, pipeline ve tool orkestrasyonunu kendi sunucunda çalıştır. Docker Compose tek komut, dakikalar içinde kurulum (warm-boot 16 saniye).";

const primaryCta = { text: "Demo İncele", href: "#demo" };

export default function HomePage() {
  return (
    <>
      <main>
        <Hero
          title={heroTitle}
          subtitle={heroSubtitle}
          primaryCta={primaryCta}
          secondaryCta={{ text: "İletişim", href: "#contact" }}
        />
        <Features />
        <Quotes />
        <Demo />
        <Contact />
        <FAQ />
        <Footer />
      </main>
    </>
  );
}
