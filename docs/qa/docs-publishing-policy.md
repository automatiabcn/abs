# Docs Publishing Policy (T-R07)

`docs.automatiabcn.com` is the canonical home for ABS Server documentation.
This policy explains the build chain, version strategy, and search setup so the
docs site stays as well-cared-for as the product itself.

## Stack

| Layer | Tool | Why |
|---|---|---|
| Static site generator | MkDocs Material 9.5+ | best Python-native docs UX, dark/light themes, search |
| Versioning | [mike](https://github.com/jimporter/mike) | publishes `gh-pages` per version + `latest` alias, no manual git ops |
| Search | Algolia DocSearch (managed) | indexes daily, free for OSS docs, accessible UX |
| API reference | [Scalar](https://scalar.com/) | interactive OpenAPI viewer, reads live `/openapi.json` |

## Build chain

`scripts/build_docs.sh` regenerates `docs/api-reference.md` from MCP tool annotations, then `mkdocs build` writes the static site to `site/` (gitignored).

In CI, `.github/workflows/docs.yml`:
1. Runs the regen script.
2. Uses `mike deploy --push --update-aliases <version> latest` to push to the `gh-pages` branch.
3. `mike set-default --push latest` keeps the root URL pointing at the most recent release.

## Version strategy

- Every release tag (`v1.0.0`, `v1.1.0`, …) triggers a docs build labelled with that version.
- The `latest` alias always points to the most recent release.
- A `next` alias tracks `main` after each merge for in-flight features.
- Old versions stay reachable forever via `https://docs.automatiabcn.com/v1.0.0/`.

## Search

DocSearch crawler config lives in the Algolia dashboard (`abs-docs` index). Two repo secrets are required:

- `ALGOLIA_APP_ID` — your application id (public-safe).
- `ALGOLIA_SEARCH_KEY` — public search-only API key (safe to ship in HTML).

A separate **admin key** lives only in the Algolia dashboard for crawler runs.

## Local preview

```bash
pip install \
  "mkdocs-material[imaging]>=9.5" \
  "mike>=2.1" \
  "mkdocs-algolia-docsearch>=0.4"

# regenerate api-reference.md from MCP tool annotations
bash scripts/build_docs.sh

# live-preview (auto-reload)
mkdocs serve

# version-aware preview
mike deploy --update-aliases dev latest
mike serve
```

## Strict build

CI runs `mkdocs build --strict` for PRs. Any broken link, missing nav reference, or invalid frontmatter breaks the build.

## What ships in `nav`

The mkdocs.yml `nav:` block is the shipped table of contents. Sections shipped today:

- Setup Guide / Quickstart / Architecture / API Reference (Scalar + static)
- Operations runbooks (billing, first-customer, troubleshooting, DR, vault, webhook rotation, performance)
- Security (scope, OWASP+RAG checklist, OAuth pen-test, HackerOne)
- Design (decisions, vision, open questions)
- Launch (GA checklist, press kit, copy, A/B, crisis comm)
- QA & Policy (perf budget, i18n policy, fs-scan allowlist, bug reports, bundle reports)
- FAQ + CHANGELOG + Research

Adding a new doc: drop the `.md` under `docs/`, append it to `nav:`, run `mkdocs build --strict` locally, ship the PR.

## Migrating from `docs.abs.automatiabcn.com`

Sprint 19 will configure DNS at `docs.automatiabcn.com` to point at the GitHub Pages site. Until then, the workflow publishes to the existing `gh-pages` branch and the legacy URL keeps working.
