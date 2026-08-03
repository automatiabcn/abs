# ABS Studio — servidor

🇬🇧 [English](README.md) · 🇹🇷 [Türkçe](README.tr.md) · 🇪🇸 **Español**

> La mitad servidor de ABS Studio: el editor corre en tu máquina, esto corre en tu
> VPS, y entre medias no hay nada nuestro. Este lado aporta los proveedores, la
> recuperación, las herramientas y la facturación. **$5 al mes**, siete días de
> prueba sin tarjeta, cancela cuando quieras.
>
> ¿Buscas el editor? [app.automatiabcn.com](https://app.automatiabcn.com/studio).

## Por qué un servidor aparte

Un editor con IA que lo guarda todo en el portátil no puede buscar en tus documentos,
no recuerda la reunión de la semana pasada y se detiene en cuanto un proveedor tiene
un mal día. Un editor que lo envía todo a un proveedor resuelve eso, y a cambio le
entrega tu código.

Esta es la tercera respuesta: el editor habla con un servidor que es tuyo.

- Enrutado entre **7 proveedores** con cortacircuitos: la caída de uno no es la tuya;
  y recurre a modelos locales (Ollama, MLX) si los tienes.
- **157 herramientas MCP**: recuperación híbrida RAG, judge persona ML, modo
  desarrollador fullstack, canal de calidad en turco.
- Todo en **tu máquina**. Nada llega a servidores de Automatia; lo único que sale son
  las llamadas que tú haces a un proveedor, con tu clave.

## Instalación rápida

Necesitas un VPS Linux (un Hetzner CX22 de $5 al mes basta) y Docker.

```bash
ssh root@vps-ip
curl -fsSLO https://app.automatiabcn.com/download   # el archivo del servidor
tar -xzf abs-server-*.tar.gz && cd abs-server-*
./install.sh                                        # escribe .env, vuelve a ejecutarlo
```

La primera ejecución escribe un `.env` para que lo completes —tu dominio y una
dirección de administrador— y la segunda descarga las imágenes publicadas y lo
levanta todo detrás de Caddy, que obtiene su propio certificado. No se compila nada
desde el código y los primeros siete días no piden clave de licencia.

Detalles: [Guía de instalación](docs/setup-guide.md) ·
[Precios](https://app.automatiabcn.com/pricing)
