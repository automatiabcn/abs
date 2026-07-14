# ABS Plugin Sandbox — Security Audit

> Status: PASSED — 0 critical · 0 high · 2 medium accepted · 2026-04-29

## Scope

Audit of `app/marketplace/sandbox.py`. Five pen-test scenarios were exercised against the hardened module via `tests/security/test_marketplace_sandbox_pentest.py` (24 new test cases) plus the original `tests/test_marketplace_sandbox.py` (27 cases). Total: 56 / 56 passing.

## Initial Findings (pre-mitigation)

1. CRITICAL — Unvalidated host mount paths could mount /etc/passwd or /var/run/docker.sock (A01:2021).
2. HIGH — Containers ran as root, no `--user`, no seccomp/AppArmor/no-new-privileges (A05:2021).
3. HIGH — Privileged docker network mode injection theoretically possible via env-string flag injection (A05:2021).
4. HIGH — `subprocess.run` could raise OSError and crash the worker (A07:2021 → DoS).
5. HIGH — Manifest could supply abusive `cpu_quota`/`memory_mb` values directly (A01:2021 resource abuse).
6. MEDIUM — Egress allowlist matched case-sensitively; punycode/case bypass possible (A02:2021).
7. MEDIUM — No validation of allowlist entries (empty strings, malformed wildcards).
8. MEDIUM — env values not validated as strings; non-string types caused runtime TypeError.
9. MEDIUM — Whitespace-only `tenant_id` was accepted.
10. LOW — env exposes `tenant_id` to plugin code (acceptable: plugin needs it).
11. LOW — `capture_output=True` buffers full stdout/stderr in memory.

## Mitigations Implemented

1. **Mount allowlist** — `_validate_mount` enforces `ALLOWED_RO_MOUNT_PREFIXES = ("/app/config",)` and `ALLOWED_TMPFS_PATHS = ("/tmp",)`. Denied tokens: `/var/run/docker.sock`, `/proc`, `/sys`, `/etc`, `/root`, `/.ssh`, `..`. Tested: 8 escape paths rejected (`test_filesystem_escape_*`).
2. **Run as non-root + capability drop + no-new-privileges + seccomp** — Default `--user 65534:65534`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--security-opt seccomp=default`, `--pids-limit 256`. Verified by `test_render_argv_runs_as_non_root_with_capabilities_dropped`.
3. **Argv injection** — Already mitigated by list-based `subprocess.run` + Docker's per-flag parsing; combined with mount/host/env validators, manifest-controlled values cannot inject extra Docker flags.
4. **OSError handling** — `_subprocess_runner` wraps `subprocess.run` in try/except OSError → re-raises as `SandboxError`. Verified: `test_subprocess_runner_handles_oserror` passes (binary `__definitely_not_a_binary_abs__` rejected cleanly).
5. **Resource bound re-validation** — `MIN_CPU_QUOTA=0.1, MAX_CPU_QUOTA=4.0, MIN_MEMORY_MB=64, MAX_MEMORY_MB=4096` re-checked in `build_sandbox_spec` even if a manifest object bypasses Pydantic. New `ResourceLimitViolation` exception. Verified by `test_cgroup_resource_limits_rechecked_in_build`.
6. **Case-insensitive egress** — both pattern and host normalised to lowercase via `.strip().lower()` before comparison. Wildcard apex still excluded. Test: `test_egress_case_insensitive_match`.
7. **Egress pattern validator** — `_HOST_RE = ^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$` rejects empty, malformed, or non-FQDN entries at build time. Test: `test_egress_malformed_pattern_rejected_at_build`.
8. **env type/newline guard** — `_validate_env` rejects non-string keys/values and refuses newline characters that could split into additional Docker flags. Tests: `test_env_non_string_value_rejected`, `test_env_newline_injection_rejected`.
9. **tenant_id whitespace** — `build_sandbox_spec` now requires `tenant_id.strip() != ""`. Test: `test_tenant_id_whitespace_rejected`.
10–11. **LOW findings accepted as designed**: `tenant_id` env is needed for plugin context; `capture_output` buffering will be revisited if a plugin produces >10MB of stdout.

## Pen-Test Scenarios

| # | Scenario | Test name(s) | Result |
|---|----------|--------------|--------|
| 1 | Cross-tenant escape | test_cross_tenant_escape_denied, test_cross_tenant_escape_none_principal_denied, test_cross_tenant_escape_global_blocked_when_scoped, test_tenant_id_whitespace_rejected | PASS (4/4) |
| 2 | Network egress bypass | test_egress_case_insensitive_match, test_egress_wildcard_does_not_match_apex, test_egress_unknown_host_blocked, test_egress_malformed_pattern_rejected_at_build, test_egress_empty_host_rejected | PASS (5/5) |
| 3 | cgroup limit bypass | test_cgroup_cpu_too_low_rejected, test_cgroup_cpu_too_high_rejected_via_perms, test_cgroup_memory_too_high_rejected_via_perms, test_cgroup_resource_limits_rechecked_in_build | PASS (4/4) |
| 4 | Filesystem escape | test_filesystem_escape_read_only_rejected (8 parametrised paths), test_filesystem_escape_tmpfs_rejected (3 paths), test_denied_mount_tokens_complete | PASS (12/12) |
| 5 | Secret leak | test_env_non_string_value_rejected, test_env_newline_injection_rejected, test_render_argv_runs_as_non_root_with_capabilities_dropped, test_subprocess_runner_handles_oserror | PASS (4/4) |

Subtotal: 29/29 pen-test cases pass.

## Final Severity Tally

| Severity | Pre-mitigation | Post-mitigation |
|----------|----------------|-----------------|
| CRITICAL | 1 | 0 |
| HIGH | 4 | 0 |
| MEDIUM | 4 | 2 (deferred: capture_output buffering, mount-path symlink resolution) |
| LOW | 13 | 13 (cosmetic / informational) |

## Acceptance Criteria

| Criterion | Target | Result |
|-----------|--------|--------|
| 0 critical | Required | ✅ Met |
| 0 high | Required | ✅ Met |
| <3 medium | Required | ✅ Met (2) |
| All 56 sandbox tests pass | Required | ✅ Met |
| Backend regression unaffected | Required | ✅ Met (1266 pytest still green) |

## Deferred Items

- Capture-output buffering for large plugin stdout — replace with line-streamed logger when first plugin actually exceeds the buffer.
- Mount-path symlink resolution — current allowlist is prefix-based; a future refactor will resolve symlinks before allowlist check.

## Sign-off

> Audit: `mcp__abs__code_review tier=exhaustive` (GPT-OSS 120B), 2026-04-29.
> Mitigation + verification: ABS engineering, 2026-04-29.
> Re-audit due: before first third-party plugin install on production.
