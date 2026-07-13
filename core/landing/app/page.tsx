/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import Demo from "@/components/Demo";
import FAQ from "@/components/FAQ";
import Features from "@/components/Features";
import Footer from "@/components/Footer";
import Hero from "@/components/Hero";
import Quotes from "@/components/Quotes";
import Contact from "@/components/Contact";

const heroTitle = "100+ MCP tools and a 6-provider cascade on your own server — one package, your infrastructure.";

const heroSubtitle = "Automatia ABS: turn chaos into automation, on your own server. 100+ MCP tools, a 6-provider cascade and quality pipelines. It runs on your own Anthropic Claude key, and your data stays with you.";

const primaryCta = { text: "Watch the demo", href: "#demo" };

export default function HomePage() {
  return (
    <>
      <main>
        <Hero
          title={heroTitle}
          subtitle={heroSubtitle}
          primaryCta={primaryCta}
          secondaryCta={{ text: "Contact", href: "#contact" }}
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
