# Contributing to Automatia ABS

Thanks for considering a contribution. ABS is a small project; your patches are
welcome and reviewed quickly.

## Workflow

1. **Fork** the repo on GitHub.
2. **Branch** off `main` (`git checkout -b fix/short-description`).
3. **Code + test.** Backend tests live in `core/backend/tests/`, frontend in
   `core/landing/__tests__/`.
4. **Run the suite locally:**
   ```bash
   cd core/backend && .venv/bin/pytest -q
   cd core/landing && npm test
   ```
5. **PR** against `main`. The PR template will ask you for the change rationale,
   tests added/updated, and any breaking-change notes.
6. **Two maintainer reviews + green CI** before merge. We squash-merge.

## Style

- **Backend:** Python 3.13, type hints required for public functions, ruff/black
  formatting. No new dependencies without justification in the PR.
- **Frontend:** TypeScript strict, React 19 + Tailwind 3. Follow existing component
  patterns in `core/landing/components/`.
- **Commits:** follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- **Tests:** new code must come with tests. We do not accept "trust me, it works".

## Areas where we welcome help

- New MCP tool implementations (see `app/mcp/tools/` for examples).
- Provider integrations (see `app/providers/` — current 6 cascade).
- Locale translations (`app/i18n/locales/`, `core/landing/locales/`).
- Documentation in `docs/` and the MkDocs site.
- Performance benchmarks and profiling.
- Accessibility improvements (Lighthouse audits welcome).

## Areas that are out of scope (for now)

- Architecture-level refactors without prior discussion.
- New billing models — pricing strategy is owner-driven.
- Premium add-on contributions — contact us first if interested.

## Questions?

Open a [GitHub Discussion](https://github.com/automatiabcn/abs/discussions) or email
[support@automatiabcn.com](mailto:support@automatiabcn.com).

By contributing, you agree your contribution is licensed under
[Apache 2.0](LICENSE).
