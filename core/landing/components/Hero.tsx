import Link from "next/link";
import type { FC } from "react";

import HeroVisual from "./HeroVisual";

interface HeroCta {
  text: string;
  href: string;
}

export interface HeroProps {
  title: string;
  subtitle: string;
  primaryCta: HeroCta;
  secondaryCta: HeroCta;
}

const Hero: FC<HeroProps> = ({ title, subtitle, primaryCta, secondaryCta }) => (
  <section
    aria-labelledby="hero-title"
    className="relative overflow-hidden min-h-[640px]"
  >
    {/* Animated gradient background — pure CSS, no JS */}
    <div
      aria-hidden="true"
      className="absolute inset-0 -z-20 bg-gradient-to-br from-primary/10 via-background to-purple-500/10"
    />
    <div
      aria-hidden="true"
      className="absolute inset-0 -z-20 bg-[radial-gradient(circle_at_50%_-20%,rgba(30,87,172,0.18),transparent_60%)]"
    />
    {/* T-Q05 — 3D scene on desktop / static SVG on mobile + reduced-motion */}
    <HeroVisual />

    <div className="container relative mx-auto grid gap-12 px-4 py-24 sm:py-32 lg:grid-cols-2 lg:items-center">
      <div className="max-w-2xl">
        <h1
          id="hero-title"
          className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl"
        >
          {title}
        </h1>
        <p className="mt-6 text-lg leading-relaxed text-muted-foreground sm:text-xl">
          {subtitle}
        </p>
        <div className="mt-10 flex flex-col items-start gap-4 sm:flex-row">
          <Link
            href={primaryCta.href}
            className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {primaryCta.text}
          </Link>
          <Link
            href={secondaryCta.href}
            className="inline-flex h-11 items-center justify-center rounded-md border border-input bg-transparent px-8 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {secondaryCta.text}
          </Link>
        </div>
      </div>
    </div>
  </section>
);

export default Hero;
