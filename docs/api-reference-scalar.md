# API Reference — Interactive

This page renders the ABS public API via [Scalar](https://scalar.com/), reading the live OpenAPI spec the FastAPI backend exposes at `/openapi.json`.

<div id="scalar-api-reference"></div>

<script
  id="api-reference"
  data-url="https://api.automatiabcn.com/openapi.json"
  data-configuration='{"theme":"saturn","layout":"modern","hideClientButton":false,"darkMode":true}'
></script>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>

> If the spec hasn't loaded, your browser blocked `cdn.jsdelivr.net`. Try an
> incognito window or check your network. The spec itself is also browsable
> at <https://api.automatiabcn.com/openapi.json>.

## Local development

When running ABS locally:

```bash
cd core/backend
./.venv/bin/uvicorn app.main:app --reload
```

The OpenAPI spec is then at <http://localhost:8000/openapi.json> and the
auto-generated Swagger UI at <http://localhost:8000/docs>. Replace the
`data-url` above with the local URL when working offline.

## Static fallback

The static `api-reference.md` (auto-generated from MCP tool annotations) lives
alongside this page for environments where the Scalar runtime can't load.
