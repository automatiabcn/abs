import Demo from "@/components/Demo";
import FAQ from "@/components/FAQ";
import Features from "@/components/Features";
import Footer from "@/components/Footer";
import Hero from "@/components/Hero";
import Quotes from "@/components/Quotes";
import Contact from "@/components/Contact";

const heroTitle = "Kendi sunucunda 100+ MCP tool ve 6 sağlayıcı cascade — tek paket, kendi altyapın.";

const heroSubtitle = "Automatia ABS: kaosu otomasyona dönüştür, kendi sunucunda. 100+ MCP tool + 6 sağlayıcı cascade + kalite pipeline'ları. Anthropic Claude key'inle çalışır, veri tamamen sende kalır.";

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
