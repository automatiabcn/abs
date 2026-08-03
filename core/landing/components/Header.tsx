/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sticky glass header with AbsLogo, primary nav, and theme toggle.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
// Phosphor subpath SSR imports keep the icon footprint out
// of the shared first-load chunk (target: shared < 100 KB gzip).
import { Moon } from "@phosphor-icons/react/dist/ssr/Moon";
import { SunHorizon } from "@phosphor-icons/react/dist/ssr/SunHorizon";

import AbsLogo from "@/components/icons/AbsLogo";
import ManageModal from "./ManageModal";

// /showcase is an internal design-system gallery (token swatches, brand icons)
// — a developer reference, not a customer surface. The route stays reachable by
// direct URL; it just doesn't belong in the nav a buyer reads.
const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/pricing", label: "Pricing" },
  { href: "/beta", label: "Beta" },
] as const;

// On the editor's own pages the menu offers the next step a visitor there
// actually wants — the build and how to install it — rather than the way back
// out to the platform.
const PRODUCT_NAV_LINKS = [
  { href: "/studio", label: "Overview" },
  { href: "/download", label: "Download" },
  { href: "/docs/install", label: "Install" },
  { href: "/docs/guide", label: "Guide" },
  { href: "/pricing", label: "Pricing" },
] as const;

function useScrolled(threshold = 8): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);
  return scrolled;
}

function applyTheme(theme: "light" | "dark") {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.classList.toggle("light", theme === "light");
}

function ThemeToggle() {
  const [isLight, setIsLight] = useState(false);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const saved = (() => {
      try {
        return localStorage.getItem("abs-theme");
      } catch (_e) {
        return null;
      }
    })();
    // Respect server-rendered class first (set from cookie in
    // layout.tsx). Only flip if the user has an explicit saved preference.
    const serverIsLight = document.documentElement.classList.contains("light");
    const initial: "light" | "dark" =
      saved === "light"
        ? "light"
        : saved === "dark"
          ? "dark"
          : serverIsLight
            ? "light"
            : "dark";
    setIsLight(initial === "light");
    applyTheme(initial);
  }, []);

  const toggle = () => {
    const next = isLight ? "dark" : "light";
    setIsLight(next === "light");
    applyTheme(next);
    try {
      localStorage.setItem("abs-theme", next);
      // Server can read this cookie on next render to avoid FOUC.
      document.cookie = `abs-theme=${next}; max-age=${60 * 60 * 24 * 365}; path=/; samesite=lax`;
    } catch (_e) {
      // localStorage / cookie unavailable; non-fatal.
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isLight ? "Switch to dark theme" : "Switch to light theme"}
      className="grid h-9 w-9 place-items-center rounded-md border transition-colors"
      style={{
        borderColor:
          "color-mix(in oklch, var(--abs-foreground) 18%, transparent)",
        background:
          "color-mix(in oklch, var(--abs-surface-raised) 80%, transparent)",
        color: "var(--abs-foreground)",
      }}
    >
      {isLight ? (
        <SunHorizon size={18} weight="duotone" />
      ) : (
        <Moon size={18} weight="duotone" />
      )}
    </button>
  );
}

// Routes where the product lives. The marketing header used to render over
// these too, so an operator working in the panel saw two headers stacked —
// a "Pricing / Beta" nav bar sitting on top of their own console. The panel
// carries its own chrome; the site header stays on the site.
const APP_ROUTE_PREFIXES = ["/panel", "/admin"] as const;

// Pages that belong to ABS Studio rather than to the platform around it.
const PRODUCT_ROUTE_PREFIXES = ["/studio", "/download", "/docs"] as const;

export default function Header() {
  const pathname = usePathname();
  const scrolled = useScrolled();

  const isAppRoute = APP_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname?.startsWith(`${prefix}/`),
  );
  if (isAppRoute) return null;

  // One name everywhere (founder's decision, 08-03). The split that used to
  // live here was a stand-in for an unmade choice, and it produced exactly the
  // problem it was written to describe: a buyer reading two names on the way
  // to one purchase. The ROUTE distinction stays — the editor's pages have
  // their own navigation — but the name no longer moves with it.
  const isProductRoute = PRODUCT_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname?.startsWith(`${prefix}/`),
  );
  const brand = "ABS Studio";
  const brandHref = isProductRoute ? "/studio" : "/";
  const navLinks = isProductRoute ? PRODUCT_NAV_LINKS : NAV_LINKS;

  return (
    <header
      data-component="site-header"
      data-scrolled={scrolled ? "true" : "false"}
      className="sticky top-0 z-40 transition-all"
      style={{
        background: scrolled ? "var(--abs-glass-bg)" : "transparent",
        backdropFilter: scrolled ? "blur(12px) saturate(140%)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(12px) saturate(140%)" : "none",
        borderBottom: scrolled
          ? "1px solid color-mix(in oklch, var(--abs-foreground) 12%, transparent)"
          : "1px solid transparent",
      }}
    >
      <div className="container mx-auto flex h-14 items-center justify-between px-4">
        <Link
          href={brandHref}
          className="flex min-h-[44px] items-center gap-2 py-2 font-semibold tracking-tight"
          style={{ color: "var(--abs-foreground)" }}
        >
          <AbsLogo size={22} aria-hidden="true" style={{ color: "var(--abs-brand-base)" }} />
          <span className="text-sm">{brand}</span>
        </Link>

        <nav aria-label="Main menu" className="flex items-center gap-1 text-sm">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="hidden rounded-md px-3 py-1.5 text-sm transition-colors sm:inline-flex"
              style={{ color: "var(--abs-foreground)" }}
            >
              {link.label}
            </Link>
          ))}
          <ThemeToggle />
          {/* The site had no way in. "Manage" opens the Stripe billing portal —
              it is not a sign-in — so a customer who owns this server had to
              guess the URL, and the obvious guesses (/admin/login, /panel/login)
              are not pages. This is the door. */}
          <Link
            href="/login"
            className="inline-flex min-h-[44px] items-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors"
            style={{ color: "var(--abs-foreground)" }}
          >
            Sign in
          </Link>
          <ManageModal />
        </nav>
      </div>
    </header>
  );
}
