/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 Phase K — `/admin/settings` self-service tenant config. Tabs:
// General · License · Providers · Webhooks · Branding · Security.
// Each tab ships a form skeleton; live wiring against /v1/admin/secrets/*
// and /v1/license/* finishes alongside the customer journey gate (O).
"use client";

import { useEffect, useState } from "react";
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

type SetupStatus = {
  data?: {
    domain?: { domain?: string | null; ssl_mode?: string | null } | null;
    admin?: { email?: string | null } | null;
  } | null;
};

function GeneralTab() {
  // BUG-22 — pre-fix the form rendered "Acme Corp" / "acme" / "abs.acme.com"
  // as hard-coded demo data, which made customers think their setup wizard
  // input was lost. The wizard persists `domain` + admin email under
  // /v1/setup/status, so the form now hydrates from there. Tenant name +
  // slug are not collected by the wizard yet — leave them empty rather
  // than continue to display fake demo identities.
  const [domain, setDomain] = useState<string>("");
  const [sslMode, setSslMode] = useState<string>("internal");
  const [tenantName, setTenantName] = useState<string>("");
  const [status, setStatus] = useState<SaveState>("idle");
  const [saveErr, setSaveErr] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/v1/setup/status", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: SetupStatus | null) => {
        if (cancelled || !data) return;
        const d = data?.data?.domain?.domain;
        const m = data?.data?.domain?.ssl_mode;
        if (d) setDomain(d);
        if (m) setSslMode(m);
      })
      .catch(() => undefined);
    // Hydrate the real tenant name so it survives reloads.
    fetch("/v1/admin/tenant", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!cancelled && j?.name) setTenantName(j.name);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveGeneral() {
    setStatus("saving");
    setSaveErr(null);
    try {
      const r = await fetch("/v1/admin/tenant", {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: tenantName }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setSaveErr(e instanceof Error ? e.message : "unknown");
    }
  }

  return (
    <div className="space-y-4">
      <FormRow label="Tenant adı" hint="Müşteri görünür ad">
        <Input
          value={tenantName}
          onChange={(e) => setTenantName(e.target.value)}
          placeholder="Henüz yapılandırılmadı"
          data-test="settings-tenant-name"
          aria-label="Tenant adı"
        />
      </FormRow>
      <FormRow label="Slug" hint="URL ön eki — değiştirilemez">
        <Input
          value="default"
          disabled
          className="font-mono"
          aria-label="Slug"
        />
      </FormRow>
      <FormRow label="Domain" hint="Caddy reverse proxy hedefi">
        <Input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="Henüz yapılandırılmadı"
          data-test="settings-domain"
          aria-label="Domain"
        />
      </FormRow>
      <FormRow label="SSL durumu">
        <Badge variant="outline" className="border-emerald-500/40 text-emerald-300">
          {sslMode === "acme" ? "Otomatik (Let's Encrypt)" : "Internal (self-signed)"}
        </Badge>
      </FormRow>
      <div className="flex items-center gap-3">
        <Button
          data-test="settings-save-general"
          onClick={saveGeneral}
          disabled={status === "saving"}
        >
          {status === "saving" ? "Kaydediliyor…" : status === "saved" ? "Kaydedildi ✓" : "Kaydet"}
        </Button>
        {saveErr && <span className="text-xs text-rose-400">{saveErr}</span>}
      </div>
    </div>
  );
}

// Polish round R6 — shape returned by GET /v1/license/info. Fields are
// nullable for the demo branch (no key configured yet).
type LicenseInfo = {
  status: "demo" | "licensed" | "expired" | "invalid" | "revoked";
  tier: string | null;
  jti: string | null;
  seat_count: number | null;
  expires_at: string | null;
  customer_id: string | null;
  demo: { remaining_seconds?: number; expired?: boolean } | null;
};

function maskJti(jti: string): string {
  // JTIs are usually 32+ chars; show "…" + last 8.
  if (jti.length <= 8) return jti;
  return `…${jti.slice(-8)}`;
}

function LicenseTab() {
  const [info, setInfo] = useState<LicenseInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string>("");
  const [activateState, setActivateState] = useState<"idle" | "submitting" | "ok" | "error">("idle");
  const [activateMessage, setActivateMessage] = useState<string>("");

  async function reload() {
    try {
      const res = await fetch("/v1/license/info", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as LicenseInfo;
      setInfo(json);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "fetch failed");
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function handleActivate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingKey.trim()) return;
    setActivateState("submitting");
    setActivateMessage("");
    try {
      const res = await fetch("/v1/license/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: pendingKey.trim() }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      setActivateState("ok");
      setActivateMessage("Lisans aktive edildi.");
      setPendingKey("");
      await reload();
    } catch (err) {
      setActivateState("error");
      setActivateMessage(err instanceof Error ? err.message : "Aktivasyon başarısız.");
    }
  }

  if (loadError) {
    return (
      <div data-test="license-tab" className="space-y-3 text-sm">
        <p className="text-destructive">Lisans bilgisi yüklenemedi: {loadError}</p>
        <Button onClick={() => void reload()} variant="outline">
          Tekrar dene
        </Button>
      </div>
    );
  }

  if (!info) {
    return (
      <div data-test="license-tab" className="text-sm text-muted-foreground">
        Yükleniyor…
      </div>
    );
  }

  const isDemo = info.status === "demo";
  const tierLabel = info.tier ?? "—";
  const seatLabel = info.seat_count !== null ? String(info.seat_count) : "—";
  const expiresLabel = info.expires_at
    ? new Date(info.expires_at).toLocaleDateString("tr-TR")
    : "—";
  const jtiLabel = info.jti ? maskJti(info.jti) : "—";

  return (
    <div data-test="license-tab" className="space-y-4 text-sm">
      <div className="space-y-3">
        <FormRow label="Durum">
          <Badge
            data-test="license-status"
            variant={info.status === "licensed" ? "default" : "outline"}
          >
            {info.status}
          </Badge>
        </FormRow>
        <FormRow label="Tier">
          <Badge data-test="license-tier" variant="outline">
            {tierLabel}
          </Badge>
        </FormRow>
        <FormRow label="JTI">
          <code
            data-test="license-jti"
            className="rounded bg-muted px-2 py-1 font-mono text-xs"
          >
            {jtiLabel}
          </code>
        </FormRow>
        <FormRow label="Seat limiti">
          <span data-test="license-seats">{seatLabel}</span>
        </FormRow>
        <FormRow label="Bitiş">
          <span data-test="license-expires">{expiresLabel}</span>
        </FormRow>
        {info.customer_id && (
          <FormRow label="Müşteri ID">
            <code className="rounded bg-muted px-2 py-1 font-mono text-xs">
              {info.customer_id}
            </code>
          </FormRow>
        )}
      </div>

      {isDemo && (
        <div
          data-test="license-demo-banner"
          className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-amber-200"
        >
          Demo modda çalışıyorsunuz. Lisans aktivasyonu için aşağıdaki forma
          token&apos;ınızı yapıştırın.
        </div>
      )}

      <form
        data-test="license-activation-form"
        onSubmit={handleActivate}
        className="space-y-2"
      >
        <label className="block text-xs font-medium text-muted-foreground">
          Lisans token&apos;ı yapıştır
        </label>
        <textarea
          data-test="license-activation-input"
          aria-label="Lisans token"
          value={pendingKey}
          onChange={(event) => setPendingKey(event.target.value)}
          rows={3}
          placeholder="eyJhbGciOi..."
          className="w-full rounded-md border border-input bg-background p-2 font-mono text-xs"
        />
        <div className="flex items-center gap-3">
          <Button
            type="submit"
            data-test="license-activate-button"
            disabled={activateState === "submitting" || pendingKey.trim() === ""}
          >
            {activateState === "submitting" ? "Aktive ediliyor…" : "Aktive et"}
          </Button>
          {activateState === "ok" && (
            <span className="text-xs text-emerald-400" data-test="license-activate-ok">
              {activateMessage}
            </span>
          )}
          {activateState === "error" && (
            <span className="text-xs text-destructive" data-test="license-activate-error">
              {activateMessage}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

// Polish round R7 — capitalised labels, password inputs, real status
// badge from /v1/admin/providers/status. Test button stays inert until a
// /v1/providers/{id}/test endpoint lands; for now it surfaces a friendly
// "henüz uygulanmadı" toast instead of a broken silent click.
type ProviderStatus = {
  id: string;
  label: string;
  configured: boolean;
};

function ProvidersTab() {
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/v1/admin/providers/status", {
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as { providers: ProviderStatus[] };
        if (!cancelled) setProviders(json.providers);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "fetch failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p className="text-sm text-destructive" data-test="providers-error">
        Sağlayıcı durumu yüklenemedi: {error}
      </p>
    );
  }

  if (!providers) {
    return (
      <p className="text-sm text-muted-foreground" data-test="providers-loading">
        Yükleniyor…
      </p>
    );
  }

  // No-duplicate-widgets: key entry + live test + cascade order all live on
  // the canonical /admin/providers page (ProviderConfigModal). This tab is a
  // read-only status overview that links there, instead of a half-built
  // duplicate with an inert "Test" button + an unsaved key input.
  return (
    <div className="space-y-3">
      <div className="flex flex-col items-start justify-between gap-2 rounded-md border border-border bg-card/40 p-3 text-xs text-muted-foreground sm:flex-row sm:items-center">
        <span>
          Anahtar girişi, canlı test ve cascade sırası için Sağlayıcılar
          sayfasını kullanın.
        </span>
        <a
          href="/admin/providers"
          data-test="providers-manage-link"
          className="inline-flex shrink-0 items-center rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent"
        >
          Sağlayıcıları Yönet →
        </a>
      </div>
      <ul className="space-y-2">
        {providers.map((p) => (
          <li
            key={p.id}
            data-test="provider-config-row"
            data-provider={p.id}
            className="flex items-center justify-between rounded-md border border-border bg-card/40 p-3"
          >
            <span className="text-sm font-medium">{p.label}</span>
            <Badge
              data-test={`provider-status-${p.id}`}
              variant={p.configured ? "default" : "outline"}
              className={cn(
                "text-[10px]",
                p.configured
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                  : "border-amber-500/40 text-amber-200",
              )}
            >
              {p.configured ? "Yapılandırıldı" : "Eksik"}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

type SaveState = "idle" | "saving" | "saved" | "error";

// Generic /admin/settings/{section} persistence — hydrate on mount + PUT on
// save. Closes the dead-Save-button gap on Webhooks/Alerts/Security.
function useSettingsSection<T extends Record<string, unknown>>(
  section: string,
  defaults: T,
) {
  const [data, setData] = useState<T>(defaults);
  const [status, setStatus] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/v1/admin/settings/${section}`, { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (cancelled || !j?.data) return;
        setData((prev) => ({ ...prev, ...j.data }));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [section]);

  const setField = (k: keyof T, v: unknown) =>
    setData((prev) => ({ ...prev, [k]: v }));

  async function save() {
    setStatus("saving");
    setError(null);
    try {
      const r = await fetch(`/v1/admin/settings/${section}`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  return { data, setField, save, status, error };
}

function SaveBar({ status, error, onSave }: { status: SaveState; error: string | null; onSave: () => void }) {
  return (
    <div className="flex items-center gap-3">
      <Button data-test="settings-save" onClick={onSave} disabled={status === "saving"}>
        {status === "saving" ? "Kaydediliyor…" : status === "saved" ? "Kaydedildi ✓" : "Kaydet"}
      </Button>
      {error && <span className="text-xs text-rose-400">{error}</span>}
    </div>
  );
}

function WebhooksTab() {
  const { data, setField, save, status, error } = useSettingsSection("webhooks", {
    slack: "",
    email: "",
    discord: "",
  });
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Slack incoming" hint="Cascade event'leri">
        <Input value={data.slack} onChange={(e) => setField("slack", e.target.value)}
               placeholder="https://hooks.slack.com/…" />
      </FormRow>
      <FormRow label="Email alerts">
        <Input type="email" value={data.email} onChange={(e) => setField("email", e.target.value)}
               placeholder="ops@acme.com" />
      </FormRow>
      <FormRow label="Discord webhook">
        <Input value={data.discord} onChange={(e) => setField("discord", e.target.value)}
               placeholder="https://discord.com/api/webhooks/…" />
      </FormRow>
      <SaveBar status={status} error={error} onSave={save} />
    </div>
  );
}

function AlertsTab() {
  const { data, setField, save, status, error } = useSettingsSection("alerts", {
    quota_warn: 80,
    quota_crit: 95,
    latency_p95_ms: 1500,
  });
  const num = (v: string) => Number(v) || 0;
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Quota uyarı eşiği" hint="Yüzde — bu seviyede uyarı tetiklenir">
        <Input type="number" min={0} max={100} value={data.quota_warn}
               onChange={(e) => setField("quota_warn", num(e.target.value))} />
      </FormRow>
      <FormRow label="Quota kritik eşiği">
        <Input type="number" min={0} max={100} value={data.quota_crit}
               onChange={(e) => setField("quota_crit", num(e.target.value))} />
      </FormRow>
      <FormRow label="Latency p95 SLO">
        <Input type="number" value={data.latency_p95_ms}
               onChange={(e) => setField("latency_p95_ms", num(e.target.value))} />
      </FormRow>
      <SaveBar status={status} error={error} onSave={save} />
    </div>
  );
}

function BrandingTab() {
  // Branding drives the real login page (tenant.primary_color / branding_message),
  // so it persists via the dedicated /v1/admin/branding endpoint, not the
  // generic store. Logo URL is stored as a string (no upload backend yet).
  const [color, setColor] = useState("#6366f1");
  const [message, setMessage] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [status, setStatus] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/v1/admin/tenant", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (cancelled || !j) return;
        if (j.primary_color) setColor(j.primary_color);
        if (j.branding_message) setMessage(j.branding_message);
        if (j.logo_url) setLogoUrl(j.logo_url);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function save() {
    setStatus("saving");
    setError(null);
    try {
      // logo_url + primary_color live on /branding; branding_message on /tenant.
      const r1 = await fetch("/v1/admin/branding", {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ primary_color: color, logo_url: logoUrl }),
      });
      if (!r1.ok) throw new Error(`branding HTTP ${r1.status}`);
      const r2 = await fetch("/v1/admin/tenant", {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branding_message: message }),
      });
      if (!r2.ok) throw new Error(`tenant HTTP ${r2.status}`);
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Logo URL" hint="Barındırılan logo bağlantısı">
        <Input value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)}
               placeholder="https://…/logo.png" />
      </FormRow>
      <FormRow label="Brand renk">
        <Input type="color" value={color} onChange={(e) => setColor(e.target.value)}
               className="h-10 w-24" />
      </FormRow>
      <FormRow label="Login sayfası mesajı">
        <Input value={message} onChange={(e) => setMessage(e.target.value)}
               placeholder="ABS Panel — özel mesajınızı buraya girin" />
      </FormRow>
      <SaveBar status={status} error={error} onSave={save} />
    </div>
  );
}

function SecurityTab() {
  const { data, setField, save, status, error } = useSettingsSection("security", {
    magic_link_ttl_min: 15,
    session_ttl_hours: 168,
  });
  const num = (v: string) => Number(v) || 0;
  return (
    <div className="space-y-3 text-sm">
      <FormRow label="Magic-link ömrü" hint="Dakika">
        <Input type="number" value={data.magic_link_ttl_min}
               onChange={(e) => setField("magic_link_ttl_min", num(e.target.value))} />
      </FormRow>
      <FormRow label="Oturum süresi" hint="Saat">
        <Input type="number" value={data.session_ttl_hours}
               onChange={(e) => setField("session_ttl_hours", num(e.target.value))} />
      </FormRow>
      <FormRow label="2FA" hint="TOTP — Phase Q rollout">
        <Badge variant="outline">yakında</Badge>
      </FormRow>
      <FormRow label="Audience kontrolü" hint="X-ABS-Audience header zorla">
        <Badge variant="outline" className="border-emerald-500/40 text-emerald-300">
          aktif
        </Badge>
      </FormRow>
      <SaveBar status={status} error={error} onSave={save} />
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
