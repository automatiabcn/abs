// Q8 Phase K — `/admin/settings` self-service tenant config. Tabs:
// General · License · Providers · Webhooks · Branding · Security.
// Each tab ships a form skeleton; live wiring against /v1/admin/secrets/*
// and /v1/license/* finishes alongside the customer journey gate (O).
"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Bell,
  Boxes,
  Building2,
  Image as ImageIcon,
  Layers,
  Lock,
  ScrollText,
  Settings as SettingsIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Tab =
  | "general"
  | "license"
  | "providers"
  | "webhooks"
  | "alerts"
  | "branding"
  | "security";

const TABS: { id: Tab; label: string; icon: typeof SettingsIcon }[] = [
  { id: "general", label: "Genel", icon: Building2 },
  { id: "license", label: "Lisans", icon: ScrollText },
  { id: "providers", label: "Sağlayıcılar", icon: Layers },
  { id: "webhooks", label: "Webhook'lar", icon: Boxes },
  { id: "alerts", label: "Uyarılar", icon: Bell },
  { id: "branding", label: "Marka", icon: ImageIcon },
  { id: "security", label: "Güvenlik", icon: Lock },
];

function FormRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-[200px_1fr]">
      <div>
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function GeneralTab() {
  return (
    <div className="space-y-4">
      <FormRow label="Tenant adı" hint="Müşteri görünür ad">
        <Input defaultValue="Acme Corp" data-test="settings-tenant-name" />
      </FormRow>
      <FormRow label="Slug" hint="URL ön eki — değiştirilemez">
        <Input value="acme" disabled className="font-mono" />
      </FormRow>
      <FormRow label="Domain" hint="Caddy reverse proxy hedefi">
        <Input
          defaultValue="abs.acme.com"
          data-test="settings-domain"
        />
      </FormRow>
      <FormRow label="SSL durumu">
        <Badge variant="outline" className="border-emerald-500/40 text-emerald-300">
          Otomatik (Let's Encrypt)
        </Badge>
      </FormRow>
      <Button data-test="settings-save-general">Kaydet</Button>
    </div>
  );
}

function LicenseTab() {
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Tier">
        <Badge>Solo</Badge>
      </FormRow>
      <FormRow label="JTI">
        <code className="rounded bg-muted px-2 py-1 font-mono text-xs">
          jwt-…12ab34cd
        </code>
      </FormRow>
      <FormRow label="Seat limiti">
        <span>1</span>
      </FormRow>
      <FormRow label="Bitiş">
        <span>2027-04-30</span>
      </FormRow>
      <Button variant="outline">Tier yükselt (Stripe)</Button>
    </div>
  );
}

function ProvidersTab() {
  const providers = [
    { id: "groq", configured: false },
    { id: "cerebras", configured: false },
    { id: "cloudflare", configured: false },
    { id: "gemini", configured: false },
    { id: "cohere", configured: false },
    { id: "anthropic", configured: false },
  ];
  return (
    <ul className="space-y-3">
      {providers.map((p) => (
        <li
          key={p.id}
          data-test="provider-config-row"
          data-provider={p.id}
          className="grid grid-cols-1 items-center gap-2 rounded-md border border-border bg-card/40 p-3 sm:grid-cols-[140px_1fr_auto]"
        >
          <code className="font-mono text-sm">{p.id}</code>
          <Input
            type="password"
            placeholder={`${p.id} API anahtarı`}
            className="font-mono text-xs"
          />
          <Button variant="outline" size="sm">
            Test
          </Button>
        </li>
      ))}
    </ul>
  );
}

function WebhooksTab() {
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Slack incoming" hint="Cascade event'leri">
        <Input placeholder="https://hooks.slack.com/…" />
      </FormRow>
      <FormRow label="Email alerts">
        <Input type="email" placeholder="ops@acme.com" />
      </FormRow>
      <FormRow label="Discord webhook">
        <Input placeholder="https://discord.com/api/webhooks/…" />
      </FormRow>
      <Button>Kaydet</Button>
    </div>
  );
}

function AlertsTab() {
  return (
    <div className="space-y-3 text-sm">
      <FormRow
        label="Quota uyarı eşiği"
        hint="Yüzde — bu seviyede uyarı tetiklenir"
      >
        <Input type="number" defaultValue={80} min={0} max={100} />
      </FormRow>
      <FormRow label="Quota kritik eşiği">
        <Input type="number" defaultValue={95} min={0} max={100} />
      </FormRow>
      <FormRow label="Latency p95 SLO">
        <Input type="number" defaultValue={1500} />
      </FormRow>
      <Button>Kaydet</Button>
    </div>
  );
}

function BrandingTab() {
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Logo" hint="PNG / SVG, 256x256 önerilen">
        <Input type="file" accept="image/png,image/svg+xml" />
      </FormRow>
      <FormRow label="Favicon">
        <Input type="file" accept="image/png,image/x-icon" />
      </FormRow>
      <FormRow label="Brand renk">
        <Input type="color" defaultValue="#6366f1" className="h-10 w-24" />
      </FormRow>
      <FormRow label="Login sayfası mesajı">
        <Input defaultValue="Acme Corp ABS panel" />
      </FormRow>
      <Button>Kaydet</Button>
    </div>
  );
}

function SecurityTab() {
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Magic-link ömrü" hint="Dakika">
        <Input type="number" defaultValue={15} />
      </FormRow>
      <FormRow label="Oturum süresi" hint="Saat">
        <Input type="number" defaultValue={168} />
      </FormRow>
      <FormRow label="2FA" hint="TOTP — Phase Q rollout">
        <Badge variant="outline">yakında</Badge>
      </FormRow>
      <FormRow label="Audience kontrolü" hint="X-ABS-Audience header zorla">
        <Badge variant="outline" className="border-emerald-500/40 text-emerald-300">
          aktif
        </Badge>
      </FormRow>
      <Button>Kaydet</Button>
    </div>
  );
}

const TAB_CONTENT: Record<Tab, React.ComponentType> = {
  general: GeneralTab,
  license: LicenseTab,
  providers: ProvidersTab,
  webhooks: WebhooksTab,
  alerts: AlertsTab,
  branding: BrandingTab,
  security: SecurityTab,
};

export default function SettingsPage() {
  const [active, setActive] = useState<Tab>("general");
  const Active = TAB_CONTENT[active];

  return (
    <main
      data-page="admin-settings"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <SettingsIcon className="h-5 w-5 text-primary" />
          Ayarlar
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Tenant config, lisans, sağlayıcı API key'leri, webhook ve marka.
        </p>
      </motion.header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
        <nav data-test="settings-tabs" className="space-y-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setActive(t.id)}
                data-test="settings-tab"
                data-tab={t.id}
                data-active={active === t.id}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  active === t.id
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {t.label}
              </button>
            );
          })}
        </nav>
        <Card className="bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {TABS.find((t) => t.id === active)?.label}
            </CardTitle>
            <CardDescription>
              Değişiklikler tenant başına izole edilir, audit'e düşer.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Active />
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
