# Claude Code / Codex ↔ ABS Server Integration

ABS Server talks to Claude Code, Codex (or any other MCP client) over two
separate channels:

1. **MCP HTTP transport** — the `/mcp` endpoint, JSON-RPC 2.0. Once a client
   connects, it lists ABS's 122+ MCP tools. On connect the server also sends the
   "delegate to ABS" instruction in the MCP `initialize` response — so basic
   delegation is active **whichever client connects**, with no extra config.
   - Claude Code: `claude mcp add --transport http abs <url> --header "Authorization: Bearer <token>"`
   - Codex: `codex mcp add abs --url <url> --bearer-token-env-var ABS_MCP_TOKEN`
2. **Lifecycle hooks** — the `/v1/hooks/*` endpoints (Claude Code
   `~/.claude/settings.json`). `PreToolUse → /v1/hooks/quota-check` applies the
   quota gate **and** returns an active delegation nudge (via
   `additionalContext`) for sub-tasks that can be delegated.

**Local instruction file (strengthens delegation, optional but recommended):**
paste the delegation block from the panel's `/admin/mcp-tokens` page into
`~/.claude/CLAUDE.md` for Claude Code, or `~/.codex/AGENTS.md` for Codex (or
`AGENTS.md` in the project root). The content is the same; only the file name
changes per client.

Both channels use the same bearer token: the HMAC-signed
`abs_mcp_<base64>.<base64>` format issued by the `POST /v1/mcp/tokens` endpoint.

---

## 1. Generate a token

From the panel:

```
/admin/settings → MCP Tokens → "Generate new token"
```

Or via CLI:

```bash
curl -X POST https://abs.example.com/v1/mcp/tokens \
  -H "Cookie: abs_session=<panel-cookie>" \
  -H "Content-Type: application/json" \
  -d '{"label": "claude-code-laptop", "scope": "all", "ttl_days": 90}'
```

Response:

```json
{
  "token": "abs_mcp_eyJ2IjoxL...truncated...HJpfqI",
  "label": "claude-code-laptop",
  "scope": "all",
  "tenant_slug": "default",
  "expires_at": "2026-08-01T11:30:00+00:00"
}
```

`scope` is one of three values:

| scope | What it unlocks |
|-------|-----------------|
| `mcp`   | Only the `/mcp` JSON-RPC bridge |
| `hooks` | Only the `/v1/hooks/*` lifecycle callbacks |
| `all`   | Both (recommended) |

---

## 2. MCP bridge — add it to Claude Code

```bash
claude mcp add --transport http abs https://abs.example.com/mcp \
  --header "Authorization: Bearer abs_mcp_xxxxx"
```

Or per project, in `.mcp.json`:

```json
{
  "mcpServers": {
    "abs": {
      "type": "http",
      "url": "${ABS_BASE_URL}/mcp",
      "headers": {
        "Authorization": "Bearer ${ABS_MCP_TOKEN}"
      }
    }
  }
}
```

Then, in Claude Code:

```
> Summarize the Slack threads, pull the data from ABS RAG
[Claude → MCP tools/list → sees 122 tools → tools/call mcp__abs__rag_query → result]
```

Slash commands:

```
> /mcp__abs__rag extract the customer questions
> /mcp__abs__workflow start the lead-triage flow
```

---

## 3. Lifecycle hooks — optional but recommended

`~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|mcp__abs__.*",
        "hooks": [
          {
            "type": "http",
            "url": "${ABS_BASE_URL}/v1/hooks/quota-check",
            "timeout": 5,
            "headers": {"Authorization": "Bearer ${ABS_MCP_TOKEN}"}
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "http",
            "url": "${ABS_BASE_URL}/v1/hooks/audit-log",
            "timeout": 5,
            "headers": {"Authorization": "Bearer ${ABS_MCP_TOKEN}"}
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "http",
            "url": "${ABS_BASE_URL}/v1/hooks/session-start",
            "timeout": 5,
            "headers": {"Authorization": "Bearer ${ABS_MCP_TOKEN}"}
          }
        ]
      }
    ]
  }
}
```

What each hook does:

- **PreToolUse → quota-check**: Claude Code asks ABS before every risky tool
  call. If the quota is exhausted, ABS returns
  `permissionDecision: "deny"` and the tool call is blocked.
- **PostToolUse → audit-log**: every tool that runs lands in ABS's
  `customer_audit_entries` table with a `claude_code.<tool>` action. View it on
  the `/admin/audit` page.
- **SessionStart → session-start**: when a new session opens, ABS injects the
  tenant context into Claude ("You are connected to tenant X. ABS exposes 122
  tools at /mcp...").

---

## 4. Verify a token

```bash
curl https://abs.example.com/v1/mcp/tokens/verify \
  -H "Authorization: Bearer abs_mcp_xxxxx"
```

If it returns `200 {"ok": true, "tenant": "...", "scope": "...", "expires_at": "..."}`,
the token is valid.

---

## 5. Permissions and security

- The token is HMAC-SHA256 signed; the signing key is the panel
  `session_secret`. A token cannot be verified without the server, and no one
  can mint a token for another tenant.
- TTL is 365 days max. Recommended: 90 days, rotated every 30 days.
- Thanks to the scope split you can issue separate tokens for hooks (a `mcp`
  scope token for a laptop, a `hooks` scope token for a CI runner).
- If a token is lost: revoke it from the panel (a blacklist table is planned; for
  v1: rotate `session_secret`, which invalidates every token).

---

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `401 invalid_token_prefix` | The header value does not start with `Bearer abs_mcp_...` |
| `401 bad_signature` | session_secret changed, or the token came from another instance |
| `401 token_expired` | TTL expired — generate a new token |
| `403 insufficient_scope` | A `scope=mcp` token was passed to a hook endpoint |
| `connection refused` | The `/v1/hooks/*` rewrite is missing on the Caddy side |

---

**Last updated:** 2026-05-01
