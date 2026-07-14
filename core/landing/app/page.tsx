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
import Install from "@/components/Install";
import Contact from "@/components/Contact";

// The headline was 15 words and set five lines deep at desktop width, which is
// how it came to be sharing space with the 3D scene. It leads with what the
// product is now; the counts moved to the fact row under the buttons, where a
// number is worth more than it is in a sentence.
const heroTitle = "Your own AI server. Chat with it, and it does the work.";

// "Free to run" was true of a product that no longer exists. It is a monthly
// subscription with a seven-day trial, and the sentence says so — a visitor who
// finds that out after installing it has been told something we knew was false.
const heroSubtitle =
  "One package on your infrastructure: chat, 100+ tools, retrieval over your own documents, and a cascade across six providers so an outage at one of them is not an outage for you. Seven days free — no card, no key, everything switched on.";

// The primary button used to say "Watch the demo" and scroll to a box that says
// "Demo video coming soon." — the site's main call to action, pointing at
// nothing. It offers the thing that actually exists: the install.
const primaryCta = { text: "Start the trial", href: "#install" };

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
        <Install />
        {/* The testimonials that stood here were invented: three named people,
            three specific numbers, under the heading "Feedback from our first 5
            beta testers" — on the public page of a product we sell. Deleted
            rather than rewritten. It comes back when there is a real quote,
            given with permission, to put in it. */}
        <Demo />
        <Contact />
        <FAQ />
        <Footer />
      </main>
    </>
  );
}
