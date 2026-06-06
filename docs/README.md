# ABS Server — Documentation

ABS (Automatia BCN Self-host) is a self-hostable AI orchestration platform:
a unified gateway over multiple LLM providers with RAG, a knowledge graph,
meeting transcription, workflows, an admin panel, and an MCP tool surface.

## Contents

- `api-reference.md` — HTTP API reference
- `CLAUDE_CODE_INTEGRATION.md` — connecting a Claude Code / MCP client
- `vision.md` — product vision
- `dr-runbook.md`, `vault-recovery-runbook.md`, `webhook-rotation-runbook.md`,
  `billing-runbook.md` — operational runbooks
- `operations/` — onboarding and operations guides
- `runbooks/` — setup runbooks

## Quick start

See the repository root and `infra/` for Docker Compose deployment. Run the
backend test suite with `cd core/backend && python -m pytest -q`.

The product ships globally — default language is English, with TR/ES as
alternate locales.
