# fs-scan Allowlist Policy

The `.fs-scan-allowlist.yaml` file at the repo root is the single source of truth for **false-positive carve-outs** the project accepts when interpreting fs-scan output. It is informational today (the scanner does not consume the file directly) and becomes machine-readable the moment fs-scan grows config support.

## When to add an entry

Only when **all** of these hold:

1. fs-scan flags a finding in the P0 (security) or P1 (quality) category.
2. A code reviewer (other than the change author) confirms the finding is a regex false positive — the substring matches but the semantics do not.
3. Either the call site cannot be refactored without harming readability, or there is a single allowlisted helper module (e.g. `app/db/query_helpers.py`) that already encapsulates the pattern.

When the finding is a real issue, fix the issue. Do not add an allowlist entry to silence a real bug.

## Required fields

| Field | Purpose |
|---|---|
| `id` | Stable short identifier; used in PR descriptions and review notes. |
| `check` | The fs-scan check name (`eval_exec`, `hardcoded_secret`, etc.). |
| `file` / `files` | Exact file path(s) covered. Wildcards not supported. |
| `why` | Multi-line explanation of why the regex match is a false positive. **Specific** — vague entries get rejected at review. |
| `risk` | `none` / `low` / `medium`. Anything `medium` or higher needs a Sprint task to actually remove the finding, not allowlist it. |
| `review_owner` | Team or person accountable for re-reviewing each sprint. |

## Review cadence

- **Each sprint:** the review owner reads through their entries and confirms they are still false positives. Stale entries are deleted.
- **On scanner upgrade:** if fs-scan grows the ability to consume an allowlist config, this file becomes the source of truth and `.fs-scan-allowlist.yaml` is wired in directly.
- **On new check:** when fs-scan adds a new check kind, allowlist entries do not auto-extend to it. Re-evaluate.

## Current entries

See `.fs-scan-allowlist.yaml` at the repo root. As of 2026-04-29:

- `SQLMODEL_ORM_HELPER` — a single allowlisted helper module (`app/db/query_helpers.py`) contains the typed-ORM driver. All other call sites go through `first_or_none` / `all_rows`.
- `HELM_SECRET_NAME_REFS` — Helm `*Ref` keys carry K8s Secret resource names, not values. Renamed from `*Secret` so the scanner regex stops matching, but kept in the allowlist for posterity.
- `DEMO_MODE_DUMMIES` — explicit dummy strings used only by `infra/docker-compose.demo.yml`.
- `ENV_VAR_REFERENCES` — `${VAR:-default}` shell env-var expansion patterns.
- `VLLM_SELF_HOST_FALLBACK` — self-hosted vLLM ignores the api_key parameter; settings-driven with a literal fallback.

## What this is not

- This is not a backdoor for shipping real secrets. The `assert_production_safe()` check in `app/config.py` still refuses to boot in `env=prod` if any of the nine dev-insecure defaults leaked through.
- This is not a long-term plan. Prefer refactoring out of false-positive shape (as we did for the SQLModel ORM call sites) over allowlisting.
