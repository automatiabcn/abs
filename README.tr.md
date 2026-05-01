# Automatia ABS — Claude Code için self-host AI orkestrasyonu

🇬🇧 [English](README.md) · 🇹🇷 **Türkçe** · 🇪🇸 [Español](README.es.md)

> Kendi sunucunda 100+ MCP tool ve 6 sağlayıcı cascade çalıştır. $20'lık Claude Pro
> aboneliğin + $299 tek seferlik ABS = ayda $1000+ enterprise araç kombinasyonu.

Bu dosya çeviri için iskelet — son metinler 026 sonrası dolacak. Şimdilik
[ana README'ye (EN)](README.md) bakabilirsin.

## Hızlı kurulum

```bash
ssh root@vps-ip
curl -fsSL https://raw.githubusercontent.com/automatiabcn/abs/main/infra/scripts/deploy_hetzner.sh | \
    bash -s -- --domain abs.firmaadi.com --email admin@firmaadi.com
```

Detay: [Setup Guide](docs/setup-guide.md) · [Bilet Aç](https://github.com/automatiabcn/abs/issues/new)
