# ABS — Upgrade Guide

> This release contains security, user-management and MCP fixes. You never have
> to **open and hand-edit** a config file; the steps below are limited to
> *replacing* files (pulling the new ones) and running commands.

## What changed in this release

**Security (critical):**
- 🔒 **Vault encryption-at-rest now actually works.** In the previous release
  sops used the wrong format (missing `--input-type`), so provider keys were
  never written to the encrypted vault and silently fell back to a plaintext
  `.env`. Keys are now stored in an encrypted `secrets.yaml`.
- 🔒 **`/mcp` now requires a token.** Access without a token returns 401.
  (Previously the token was not enforced — anyone could call all 122 tools.)
- 🔒 **MCP token scope is enforced** (a token with the `hooks` scope cannot use
  `/mcp`).
- 🔒 **`rag_index` path restriction** — arbitrary server files (vault key, DB,
  `/etc`) can no longer be indexed (path traversal closed).
- 🔒 **Security headers** (X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, HSTS) added to Caddy.

**User management:**
- Invite flow: when SMTP is not configured, it returns a **copyable activation
  link** (no more "the invite email was sent" when it was not).
- **Multi-admin RBAC**: promoting a user to Admin from the panel grants real
  admin permissions; demoting revokes them immediately. The last active admin is
  protected. Self-signup now creates a `member` (not an admin) — the privilege
  escalation path is closed.
- New **MCP Token page** (`/admin/mcp-tokens`) — generate a token, get the
  ready-to-run Claude Code / Codex command, revoke.

**Automation:**
- **vault-init** service — generates the vault key automatically on first boot
  (the manual `init_vault.sh` step is gone).
- Cascade is free-first (groq/gemini/… → anthropic last). No extra Anthropic key
  is required.

## Upgrade steps (customer)

| Step | Command | Hand-edit a file? |
|------|---------|-------------------|
| 1. Pull the new compose + .env template | `git pull` *or* download the new `docker-compose.customer.yml` | No (replace the file) |
| 2. Pull the new images | `docker compose pull` | No |
| 3. Update the stack | `docker compose up -d` | No |

> **Why does compose have to be updated too?** The `vault-init` service is
> defined in the **compose file**, not in the image. `docker compose pull` (the
> image) alone is not enough — you must take the new compose file as well.

### MCP connection (Claude Code / Codex)
- **If you already connect with a token: there is nothing to do.** Tokens stay
  valid as long as `ABS_SESSION_SECRET` does not change.
- If you connected without a token (now rejected): generate a token on the panel
  **MCP Token** page and run the **single command** shown there:
  ```
  claude mcp add --transport http abs https://<domain>/mcp --header "Authorization: Bearer abs_mcp_..."
  ```
  This command edits `~/.claude.json` **for you** — you never open the file.
  (For Codex: `codex mcp add abs --url https://<domain>/mcp --bearer-token-env-var ABS_MCP_TOKEN`.)

## Post-upgrade checks
- [ ] `docker compose ps` — all services healthy (vault-init `exited (0)`).
- [ ] Panel → **Providers**: keys show as "Configured" (loaded from the vault).
- [ ] Panel → **MCP Token**: generate a token → `claude mcp list` → `abs ✓ Connected`.
- [ ] **Audit your existing users**: if the old release created any `role=admin`
      users through self-signup, they now gain real admin access under the new
      RBAC — review their roles under Panel → Users.

## Notes
- **Provider keys:** every customer enters **their own** keys (panel / setup
  wizard). The product ships without keys.
- **No data loss:** the keys in your existing `.env` are preserved; after the
  upgrade, re-saving a key from the panel also writes it to the encrypted vault.
