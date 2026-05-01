# Claude Code ↔ ABS Server Integration

ABS Server iki ayrı kanaldan Claude Code (veya başka MCP istemcisi) ile
konuşur:

1. **MCP HTTP transport** — `/mcp` endpoint, JSON-RPC 2.0. Claude Code
   `claude mcp add ...` ile bağlanır, ABS'in 122+ MCP tool'unu listeler.
2. **Lifecycle hooks** — `/v1/hooks/*` endpoint'leri. Müşterinin
   `~/.claude/settings.json`'una eklenir, her tool çağrısı ABS'ten
   izin/audit alır.

İkisi de aynı bearer token ile çalışır: `/v1/mcp/tokens` POST endpoint'i
tarafından üretilen HMAC imzalı `abs_mcp_<base64>.<base64>` formatında.

---

## 1. Token üret

Panel'den:

```
/admin/settings → MCP Tokens → "Yeni token üret"
```

Veya CLI:

```bash
curl -X POST https://abs.example.com/v1/mcp/tokens \
  -H "Cookie: abs_session=<panel-cookie>" \
  -H "Content-Type: application/json" \
  -d '{"label": "claude-code-laptop", "scope": "all", "ttl_days": 90}'
```

Yanıt:

```json
{
  "token": "abs_mcp_eyJ2IjoxL...truncated...HJpfqI",
  "label": "claude-code-laptop",
  "scope": "all",
  "tenant_slug": "default",
  "expires_at": "2026-08-01T11:30:00+00:00"
}
```

`scope` üç değerden biri:

| scope | Hangisini açar |
|-------|----------------|
| `mcp`   | Sadece `/mcp` JSON-RPC bridge |
| `hooks` | Sadece `/v1/hooks/*` lifecycle callback'leri |
| `all`   | İkisi de (önerilen) |

---

## 2. MCP bridge — Claude Code'a ekle

```bash
claude mcp add --transport http abs https://abs.example.com/mcp \
  --header "Authorization: Bearer abs_mcp_xxxxx"
```

Veya proje-bazlı `.mcp.json`:

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

Sonra Claude Code'da:

```
> Slack thread'lerini özetle, ABS RAG'den veri çek
[Claude → MCP tools/list → 122 tool görür → tools/call mcp__abs__rag_query → result]
```

Slash komutları:

```
> /mcp__abs__rag müşteri sorularını çıkar
> /mcp__abs__workflow lead-triage akışını başlat
```

---

## 3. Lifecycle hook'ları — opsiyonel ama önerilen

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

Açıklama:

- **PreToolUse → quota-check**: Claude Code her risky tool'dan önce
  ABS'e sorar. ABS quota tükenmişse `permissionDecision: "deny"`
  döner ve tool çağrısı engellenir.
- **PostToolUse → audit-log**: Çalışan her tool ABS'in
  `customer_audit_entries` tablosuna `claude_code.<tool>` action ile
  düşer. `/admin/audit` sayfasından görüntülenir.
- **SessionStart → session-start**: Yeni session açıldığında ABS
  tenant context'ini Claude'a inject eder ("You are connected to tenant
  X. ABS exposes 122 tools at /mcp...").

---

## 4. Token doğrula

```bash
curl https://abs.example.com/v1/mcp/tokens/verify \
  -H "Authorization: Bearer abs_mcp_xxxxx"
```

`200 {"ok": true, "tenant": "...", "scope": "...", "expires_at": "..."}`
geri dönerse token sağlam.

---

## 5. Yetki ve güvenlik

- Token HMAC-SHA256 imzalı; signing key panel `session_secret`. Server
  açılmadan token doğrulanmaz, başka bir tenant token'ı üretemez.
- TTL maks 365 gün. Önerilen: 90 gün, 30 günde bir rotate.
- Scope ayrımı sayesinde hook'lar için ayrı token üretebilirsin
  (CTO laptop'ı için `mcp` scope, CI runner için `hooks` scope).
- Token kaybolursa: panel'den ilgili token'ı revoke et (Phase Q.2'de
  blacklist tablosu eklenecek; v1 için: `session_secret`'ı rotate et,
  tüm token'lar invalid olur).

---

## Sorun giderme

| Belirti | Olası neden |
|---------|-------------|
| `401 invalid_token_prefix` | Header'da `Bearer abs_mcp_...` ile başlamayan değer |
| `401 bad_signature` | session_secret değişmiş veya token başka instance'tan |
| `401 token_expired` | TTL dolmuş — yeni token üret |
| `403 insufficient_scope` | Hook endpoint'ine `scope=mcp` token verildi |
| `connection refused` | Caddy tarafında `/v1/hooks/*` rewrite eksik |

---

**Son güncelleme:** 2026-05-01 · Q8 Phase N + P
