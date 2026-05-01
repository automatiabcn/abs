# Automatia ABS — Orquestación AI self-host para Claude Code

🇬🇧 [English](README.md) · 🇹🇷 [Türkçe](README.tr.md) · 🇪🇸 **Español**

> Ejecuta 100+ MCP tools y cascade de 6 proveedores en tu servidor. Tu plan Claude Pro
> de $20 + $299 pago único de ABS = combinación de herramientas enterprise de $1000+/mes.

Este archivo es un esqueleto para traducción — los textos finales se completarán
después de la 026. Por ahora consulta el [README principal (EN)](README.md).

## Instalación rápida

```bash
ssh root@vps-ip
curl -fsSL https://raw.githubusercontent.com/automatiabcn/abs/main/infra/scripts/deploy_hetzner.sh | \
    bash -s -- --domain abs.tu-dominio.com --email admin@tu-dominio.com
```

Detalles: [Setup Guide](docs/setup-guide.md) · [Abrir issue](https://github.com/automatiabcn/abs/issues/new)
