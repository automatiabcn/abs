/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// MCP Token yönetimi — mint + revoke. The /mcp transport now enforces these
// tokens (McpTokenAuthASGI), so the operator needs a panel surface to issue
// one and copy the Claude Code / Codex connect command. Tokens are stateless
// HMAC strings (not stored server-side), so there is no "list" — the minted
// value is shown exactly once and must be copied immediately.
"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { KeyRound, Copy, Check, Trash2, ShieldAlert, FileCode2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface MintedToken {
  token: string;
  label: string;
  scope: string;
  tenant_slug: string;
  expires_at: string;
}

interface ActiveToken {
  token_digest: string;
  label: string;
  scope: string;
  issued_by: string;
  issued_at: string;
  expires_at: string | null;
  status: string; // active | revoked | expired
}

function mcpUrl(): string {
  if (typeof window === "undefined") return "https://your-abs-host/mcp";
  return `${window.location.origin}/mcp`;
}

// Copy-paste delegation guidance for the operator's local Claude Code config
// (~/.claude/CLAUDE.md or a project ./CLAUDE.md). The /mcp server also ships
// these instructions over the MCP `initialize` response, but a local CLAUDE.md
// makes the "delegate to ABS" behaviour stronger and explicit. English by
// default — the product ships globally.
const CLAUDE_MD_BLOCK = `# Automatia ABS — delegation

ABS is connected as an MCP server with 100+ free AI tools (running on your own
provider keys, no extra Anthropic cost). Delegate substantial subtasks to ABS
instead of doing them yourself — it saves tokens and often improves quality:

- Analysis / research / reasoning   -> mcp__abs__ask_gptoss, mcp__abs__ask_gemini_pro
- Code / a single function or endpoint -> mcp__abs__ask_kimi, mcp__abs__ask_qwen3_coder
- Translation / non-English prose    -> mcp__abs__ask_qwen32b
- Fast classification / short answers -> mcp__abs__ask_groq_fast, mcp__abs__ask_scout
- Quality over speed (generate->verify->fix) -> mcp__abs__qual_code, mcp__abs__qual_analysis
- Parallel race (fastest of several) -> mcp__abs__race, mcp__abs__race_code
- Code review / unit tests / docs    -> mcp__abs__code_review, mcp__abs__write_tests, mcp__abs__write_docs
- Project knowledge base             -> mcp__abs__rag_query

Prefer ABS for these before spending your own tokens.`;

export default function McpTokensPage() {
  const [label, setLabel] = useState("");
  const [scope, setScope] = useState("all");
  const [ttlDays, setTtlDays] = useState(90);
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<MintedToken | null>(null);
  const [mintError, setMintError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const [revokeToken, setRevokeToken] = useState("");
  const [revoking, setRevoking] = useState(false);
  const [revokeMsg, setRevokeMsg] = useState<string | null>(null);

  // Multiple-token management: the issuance ledger (digest only) so the operator
  // sees and revokes every issued token without re-pasting the raw string.
  const [tokens, setTokens] = useState<ActiveToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(true);
  const [revokingDigest, setRevokingDigest] = useState<string | null>(null);

  const loadTokens = useCallback(async () => {
    setTokensLoading(true);
    try {
      const res = await fetch("/v1/mcp/tokens", { credentials: "include", cache: "no-store" });
      if (res.ok) setTokens((await res.json()) as ActiveToken[]);
    } catch {
      /* leave the list as-is on a transient error */
    } finally {
      setTokensLoading(false);
    }
  }, []);

  useEffect(() => { void loadTokens(); }, [loadTokens]);

  async function revokeByDigest(digest: string) {
    setRevokingDigest(digest);
    try {
      await fetch("/v1/mcp/tokens/revoke", {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_digest: digest }),
      });
      await loadTokens();
    } finally {
      setRevokingDigest(null);
    }
  }

  async function copy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      window.setTimeout(() => setCopied(null), 2000);
    } catch {
      /* clipboard blocked — user can select manually */
    }
  }

  async function mint() {
    if (!label.trim()) return;
    setMinting(true);
    setMintError(null);
    setMinted(null);
    try {
      const res = await fetch("/v1/mcp/tokens", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: label.trim(),
          scope,
          ttl_days: Number(ttlDays) || 90,
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        setMintError(`HTTP ${res.status}: ${t.slice(0, 200)}`);
        return;
      }
      setMinted((await res.json()) as MintedToken);
      setLabel("");
      void loadTokens();   // new token shows up in the list below
    } catch (exc) {
      setMintError(exc instanceof Error ? exc.message : "bilinmeyen hata");
    } finally {
      setMinting(false);
    }
  }

  async function revoke() {
    if (!revokeToken.trim()) return;
    setRevoking(true);
    setRevokeMsg(null);
    try {
      const res = await fetch("/v1/mcp/tokens/revoke", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: revokeToken.trim() }),
      });
      if (res.status === 204 || res.ok) {
        setRevokeMsg("✓ Token iptal edildi (blacklist'e eklendi). Artık /mcp reddedecek.");
        setRevokeToken("");
        void loadTokens();
      } else {
        setRevokeMsg(`Hata: HTTP ${res.status}`);
      }
    } catch (exc) {
      setRevokeMsg(exc instanceof Error ? exc.message : "bilinmeyen hata");
    } finally {
      setRevoking(false);
    }
  }

  const claudeCmd = minted
    ? `claude mcp add --transport http abs ${mcpUrl()} --header "Authorization: Bearer ${minted.token}"`
    : "";
  const codexCmd = minted
    ? `export ABS_MCP_TOKEN=${minted.token}\ncodex mcp add abs --url ${mcpUrl()} --bearer-token-env-var ABS_MCP_TOKEN`
    : "";

  return (
    <main data-page="admin-mcp-tokens" className="mx-auto w-full max-w-4xl px-6 py-8">
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <KeyRound className="h-5 w-5 text-primary" />
          MCP Token
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Claude Code veya Codex&apos;in <code>/mcp</code> ucuna bağlanması için
          imzalı bir entegrasyon token&apos;ı üretin. Token <strong>yalnızca
          bir kez</strong> gösterilir — hemen kopyalayın.
        </p>
      </motion.header>

      {/* ── Mint ─────────────────────────────────────── */}
      <Card className="mb-6 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yeni token üret</CardTitle>
          <CardDescription>
            Etiket bir hatırlatıcıdır (örn. &quot;emre-laptop-claude&quot;).
            Süre dolunca token reddedilir.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_140px_120px]">
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Etiket (ör. emre-claude-code)"
              data-test="mcp-token-label"
            />
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              data-test="mcp-token-scope"
              aria-label="Token kapsamı (scope)"
              className="rounded-md border border-border bg-background px-2 text-sm"
            >
              <option value="all">all (tümü)</option>
              <option value="mcp">mcp</option>
              <option value="hooks">hooks</option>
            </select>
            <Input
              type="number"
              min={1}
              max={365}
              value={ttlDays}
              onChange={(e) => setTtlDays(Number(e.target.value))}
              data-test="mcp-token-ttl"
              title="Geçerlilik (gün)"
              aria-label="Geçerlilik (gün)"
            />
          </div>
          <Button
            onClick={() => void mint()}
            disabled={minting || !label.trim()}
            data-test="mcp-token-mint"
          >
            <KeyRound className="mr-2 h-4 w-4" />
            {minting ? "Üretiliyor…" : "Token Üret"}
          </Button>

          {mintError && (
            <div
              data-test="mcp-token-error"
              className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200"
            >
              {mintError}
            </div>
          )}

          {minted && (
            <div
              data-test="mcp-token-result"
              className="space-y-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm"
            >
              <div className="text-emerald-200">
                Token üretildi — <strong>{minted.label}</strong> · scope{" "}
                {minted.scope} · son kullanım{" "}
                <span suppressHydrationWarning>
                  {new Date(minted.expires_at).toLocaleDateString("tr-TR")}
                </span>
              </div>

              <CopyRow
                label="Token"
                value={minted.token}
                copied={copied === "token"}
                onCopy={() => copy("token", minted.token)}
                testid="mcp-token-value"
              />
              <CopyRow
                label="Claude Code"
                value={claudeCmd}
                copied={copied === "claude"}
                onCopy={() => copy("claude", claudeCmd)}
                testid="mcp-token-claude"
              />
              <CopyRow
                label="Codex"
                value={codexCmd}
                copied={copied === "codex"}
                onCopy={() => copy("codex", codexCmd)}
                testid="mcp-token-codex"
              />

              <div className="rounded-md border border-emerald-500/20 bg-background/40 p-2 text-[11px] text-emerald-200/80">
                <div className="mb-1 font-medium text-emerald-200">
                  Doğrulama + kullanım örneği
                </div>
                <CopyRow
                  label="1) Bağlantıyı doğrula (Claude Code)"
                  value="claude mcp list"
                  copied={copied === "verify"}
                  onCopy={() => copy("verify", "claude mcp list")}
                  testid="mcp-token-verify"
                />
                <div className="mt-2 leading-relaxed">
                  <code>abs</code> → <strong>✓ Connected</strong> görünmeli. Sonra
                  Claude Code / Codex içinde doğrudan kullanın — örn:
                  <span className="mt-1 block rounded bg-background px-2 py-1 font-mono text-emerald-100">
                    &quot;ABS üzerinden ask_groq_fast ile şu metni özetle: …&quot;
                  </span>
                  veya Claude ağır işleri otomatik olarak ücretsiz sağlayıcılara
                  delege eder (122 araç). Ekstra Anthropic anahtarı gerekmez.
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Issued tokens (multiple) ─────────────────── */}
      <Card className="mb-6 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Üretilmiş token&apos;lar</CardTitle>
          <CardDescription>
            Birden çok token üretebilirsin (her cihaz/servis için ayrı). Raw token
            yalnızca üretimde gösterilir; buradan etiketiyle görür ve tek tıkla
            iptal edersin.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tokensLoading ? (
            <p className="text-xs text-muted-foreground">Yükleniyor…</p>
          ) : tokens.length === 0 ? (
            <p className="text-xs text-muted-foreground" data-test="mcp-tokens-empty">
              Henüz token üretilmedi.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs" data-test="mcp-tokens-list">
                <thead className="text-muted-foreground">
                  <tr className="border-b border-border">
                    <th className="py-1.5 pr-3 font-medium">Etiket</th>
                    <th className="py-1.5 pr-3 font-medium">Scope</th>
                    <th className="py-1.5 pr-3 font-medium">Üretim</th>
                    <th className="py-1.5 pr-3 font-medium">Bitiş</th>
                    <th className="py-1.5 pr-3 font-medium">Durum</th>
                    <th className="py-1.5 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {tokens.map((t) => (
                    <tr key={t.token_digest} className="border-b border-border/60 last:border-0">
                      <td className="py-1.5 pr-3 font-medium">{t.label || "—"}</td>
                      <td className="py-1.5 pr-3 font-mono">{t.scope}</td>
                      <td className="py-1.5 pr-3" suppressHydrationWarning>
                        {new Date(t.issued_at).toLocaleDateString("tr-TR")}
                      </td>
                      <td className="py-1.5 pr-3" suppressHydrationWarning>
                        {t.expires_at ? new Date(t.expires_at).toLocaleDateString("tr-TR") : "—"}
                      </td>
                      <td className="py-1.5 pr-3">
                        <span className={
                          t.status === "active" ? "text-emerald-300"
                            : t.status === "revoked" ? "text-rose-300" : "text-amber-300"
                        }>{t.status}</span>
                      </td>
                      <td className="py-1.5 text-right">
                        {t.status === "active" && (
                          <button
                            onClick={() => revokeByDigest(t.token_digest)}
                            disabled={revokingDigest === t.token_digest}
                            data-test={`mcp-token-revoke-${t.token_digest.slice(0, 8)}`}
                            className="rounded-md border border-rose-500/40 px-2 py-1 text-[11px] text-rose-300 hover:bg-rose-500/10 disabled:opacity-50"
                          >
                            {revokingDigest === t.token_digest ? "…" : "İptal"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Revoke by raw token (paste) ──────────────── */}
      <Card className="mb-6 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Trash2 className="h-4 w-4 text-rose-400" />
            Token iptal et (yapıştırarak)
          </CardTitle>
          <CardDescription>
            Sızan/eski bir token&apos;ı kara listeye alın. Bundan sonra{" "}
            <code>/mcp</code> o token&apos;ı reddeder.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={revokeToken}
            onChange={(e) => setRevokeToken(e.target.value)}
            placeholder="abs_mcp_…"
            rows={2}
            data-test="mcp-token-revoke-input"
            className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs"
          />
          <Button
            variant="outline"
            onClick={() => void revoke()}
            disabled={revoking || !revokeToken.trim()}
            className="text-rose-300"
            data-test="mcp-token-revoke"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            {revoking ? "İptal ediliyor…" : "İptal Et"}
          </Button>
          {revokeMsg && (
            <div
              data-test="mcp-token-revoke-msg"
              className="rounded-md border border-border bg-background/50 p-2 text-xs text-muted-foreground"
            >
              {revokeMsg}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Delegation / CLAUDE.md + AGENTS.md ─────────────────────── */}
      <Card className="mb-6 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCode2 className="h-4 w-4 text-primary" />
            Otomatik delegasyon (CLAUDE.md / AGENTS.md)
          </CardTitle>
          <CardDescription>
            Token bağlanınca Claude Code <em>ve</em> Codex ABS&apos;yi{" "}
            <strong>tanır</strong> (sunucu yönergeyi MCP üzerinden gönderir) ama
            alt görevleri proaktif delege etmesi için yerel bir yönerge bunu
            güçlendirir. Aynı bloğu kendi makinende yapıştır:{" "}
            <strong>Claude Code</strong> →{" "}
            <code>~/.claude/CLAUDE.md</code>, <strong>Codex</strong> →{" "}
            <code>~/.codex/AGENTS.md</code> (veya proje kökünde{" "}
            <code>AGENTS.md</code>). Hangi kullanıcı bağlanırsa bağlansın
            analiz, kod, çeviri gibi işleri ABS&apos;ye yönlendirir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CopyRow
            label="CLAUDE.md / AGENTS.md — delegasyon bloğu"
            value={CLAUDE_MD_BLOCK}
            copied={copied === "claudemd"}
            onCopy={() => copy("claudemd", CLAUDE_MD_BLOCK)}
            testid="mcp-token-claudemd"
          />
        </CardContent>
      </Card>

      <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Token&apos;lar sunucuda saklanmaz (stateless, imzalı). Bu yüzden
          listelenemez — kaybederseniz yenisini üretip eskisini iptal edin.
          <code>/mcp</code> ucu her istekte token&apos;ı doğrular.
        </span>
      </div>
    </main>
  );
}

function CopyRow({
  label,
  value,
  copied,
  onCopy,
  testid,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
  testid: string;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-emerald-200/80">{label}</div>
      <div className="flex items-start gap-2">
        <textarea
          readOnly
          value={value}
          rows={Math.min(Math.max(value.split("\n").length, 1), 16)}
          onFocus={(e) => e.currentTarget.select()}
          data-test={testid}
          className="w-full rounded border border-emerald-500/30 bg-background px-2 py-1 font-mono text-[11px] text-emerald-100"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 shrink-0 text-[11px]"
          onClick={onCopy}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </Button>
      </div>
    </div>
  );
}
