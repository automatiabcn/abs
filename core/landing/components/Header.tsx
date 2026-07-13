/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// T-R03 revise — sticky glass header with AbsLogo, primary nav, and theme toggle.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
// T-R03 fix #5 — Phosphor subpath SSR imports keep the icon footprint out
// of the shared first-load chunk (target: shared < 100 KB gzip).
import { Moon } from "@phosphor-icons/react/dist/ssr/Moon";
import { SunHorizon } from "@phosphor-icons/react/dist/ssr/SunHorizon";

import AbsLogo from "@/components/icons/AbsLogo";
import ManageModal from "./ManageModal";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/showcase", label: "Showcase" },
  { href: "/pricing", label: "Pricing" },
  { href: "/beta", label: "Beta" },
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
    // T-R03 fix #2 — respect server-rendered class first (set from cookie in
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
      // T-R03 fix #2 — server can read this cookie on next render to avoid FOUC.
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

export default function Header() {
  const pathname = usePathname();
  const scrolled = useScrolled();

  const isAppRoute = APP_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname?.startsWith(`${prefix}/`),
  );
  if (isAppRoute) return null;

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
          href="/"
          className="flex min-h-[44px] items-center gap-2 py-2 font-semibold tracking-tight"
          style={{ color: "var(--abs-foreground)" }}
        >
          <AbsLogo size={22} aria-hidden="true" style={{ color: "var(--abs-brand-base)" }} />
          <span className="text-sm">Automatia ABS</span>
        </Link>

        <nav aria-label="Main menu" className="flex items-center gap-1 text-sm">
          {NAV_LINKS.map((link) => (
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
          <ManageModal />
        </nav>
      </div>
    </header>
  );
}
