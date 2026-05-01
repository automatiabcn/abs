// Q7 Phase C — top bar with breadcrumb + theme toggle + user menu placeholder.
"use client";

import { usePathname } from "next/navigation";
import { ChevronRight, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/panel/ThemeToggle";

const LABELS: Record<string, string> = {
  panel: "Panel",
  admin: "Admin",
  meetings: "Toplantılar",
  quota: "Kota",
  transcription: "Transcription",
  marketplace: "Marketplace",
  "workflow-builder": "Workflow Builder",
};

function crumbs(pathname: string): { href: string; label: string }[] {
  const parts = pathname.split("/").filter(Boolean);
  return parts.map((part, i) => ({
    href: "/" + parts.slice(0, i + 1).join("/"),
    label: LABELS[part] ?? part,
  }));
}

export function PanelHeader() {
  const pathname = usePathname() ?? "/panel";
  const trail = crumbs(pathname);
  return (
    <header
      data-test="panel-header"
      className="flex h-14 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur"
    >
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-1 text-sm text-muted-foreground"
      >
        {trail.length === 0 ? (
          <span>Genel Bakış</span>
        ) : (
          trail.map((c, i) => (
            <span key={c.href} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 opacity-50" />}
              <span
                className={
                  i === trail.length - 1
                    ? "font-medium text-foreground"
                    : ""
                }
              >
                {c.label}
              </span>
            </span>
          ))
        )}
      </nav>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        <Button
          variant="ghost"
          size="icon"
          aria-label="User menu"
          data-test="user-menu"
        >
          <User className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
