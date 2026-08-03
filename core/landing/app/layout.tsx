/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { Geist, JetBrains_Mono } from "next/font/google";

import DemoBanner from "@/components/DemoBanner";
import Header from "@/components/Header";

import "./globals.css";

// Where the site actually is. It said `abs.` — a host that has never had a
// DNS record — so the canonical URL, the sitemap, robots.txt and every link
// preview pointed at nothing (found 08-03 walking the money path).
const SITE_URL = "https://app.automatiabcn.com";

// Modern font stack: Geist Variable display + JetBrains Mono
// for tabular metric numbers + code. Both loaded via next/font/google so
// they self-host in production (CSP-safe, no runtime fetch).
const geist = Geist({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "ABS Studio — an AI code editor that runs on your machine",
    template: "%s · ABS Studio",
  },
  description:
    "The editor you write in and the engine behind it both run on your own hardware. Your code is not uploaded to be indexed, and the panel tells you which provider answered, what it cost, and what it did not do.",
  keywords: [
    "ABS Studio",
    "AI code editor",
    "self-hosted",
    "BYOK",
    "MCP",
    "code review",
    "AI agent",
    "Automatia",
  ],
  authors: [{ name: "Automatia BCN" }],
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "ABS Studio",
    title: "ABS Studio — an AI code editor that runs on your machine",
    description:
      "Graded edits, a visible provider chain, and a workspace it actually reads. Seven-day trial, no card.",
    images: ["/og.png"],
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "ABS Studio",
    description:
      "An AI code editor that runs on your machine. Graded edits, a visible provider chain, your own keys.",
    images: ["/og.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  // Read the persisted theme cookie so first-paint matches
  // the toggle state and we avoid FOUC.
  const cookieStore = await cookies();
  const theme = cookieStore.get("abs-theme")?.value;
  const themeClass = theme === "light" ? "light" : "dark";

  return (
    <html
      lang="en"
      className={`${themeClass} ${geist.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-background font-sans text-foreground">
        <DemoBanner />
        <Header />
        {children}
      </body>
    </html>
  );
}
