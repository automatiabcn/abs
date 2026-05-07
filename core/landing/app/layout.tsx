import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { Geist, JetBrains_Mono } from "next/font/google";

import DemoBanner from "@/components/DemoBanner";
import Header from "@/components/Header";

import "./globals.css";

const SITE_URL = "https://abs.automatiabcn.com";

// T-R03 revise — modern font stack: Geist Variable display + JetBrains Mono
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
    default: "Automatia ABS — Self-hosted AI ağı",
    template: "%s · Automatia ABS",
  },
  description:
    "Kaosu otomasyona dönüştür — kendi sunucunda. 100+ MCP tool + 6 sağlayıcı cascade + kalite pipeline'ları. Anthropic Claude key'inle çalışır, veri tamamen sende kalır.",
  keywords: [
    "ABS",
    "Automatia",
    "Claude",
    "MCP",
    "self-hosted AI",
    "Anthropic",
    "Groq",
    "RAG",
    "Türkçe AI",
  ],
  authors: [{ name: "Automatia BCN" }],
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "Automatia ABS",
    title: "Automatia ABS — Self-hosted AI ağı",
    description:
      "100+ MCP tool + 6 sağlayıcı cascade. Docker Compose ile dakikalar içinde kendi sunucunda.",
    images: ["/og.png"],
    locale: "tr_TR",
  },
  twitter: {
    card: "summary_large_image",
    title: "Automatia ABS",
    description:
      "Self-hosted AI ağı: 100+ MCP tool + 6 sağlayıcı cascade. Pilot/PoC için iletişim.",
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
  // T-R03 fix #2 — read the persisted theme cookie so first-paint matches
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
