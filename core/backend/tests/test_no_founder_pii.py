"""Polish round R1 — repo-wide guard against founder PII leaks.

Brief WORKER_POLISH_ROUND.md §2 — UI strings, public docs and the top-level
README must not contain the founder's first name. Author attributions belong
to ``Automatia BCN engineering`` (collective) so the product can ship globally
without exposing a single individual.

Scope (matches brief §2 "Replacement strategy"):

* ``core/landing/`` ``*.tsx`` / ``*.ts``
* ``docs/`` ``*.md``
* top-level ``README.md``

Out of scope:

* ``CLAUDE.md`` — local operator instructions, not customer-visible.
* ``artifacts/`` — historical sprint logs, only swept opportunistically.
* Anything under ``.git/`` — git author config is fine.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# "Enes" as a standalone word; the founder's first name as it leaks into UI
# copy or doc author lines. ``re.IGNORECASE`` is intentionally OFF so that
# words like "lenses" or "tenseness" don't trigger.
FOUNDER_FIRST_NAME = re.compile(r"\bEnes\b")

# Lower-case Unix username pattern. ``re.IGNORECASE`` is ON because Windows
# would write ``Eneseserkan`` and we still want to catch it. The regex is
# anchored to the username, not the path, so it works in markdown prose too.
FOUNDER_USERNAME = re.compile(r"eneseserkan", re.IGNORECASE)


def _iter_scoped_files() -> list[Path]:
    """Yield every file that the polish-round PII guard owns."""
    targets: list[Path] = []

    landing = REPO_ROOT / "core" / "landing"
    if landing.is_dir():
        for ext in ("*.tsx", "*.ts"):
            targets.extend(
                p
                for p in landing.rglob(ext)
                if "node_modules" not in p.parts and ".next" not in p.parts
            )

    docs = REPO_ROOT / "docs"
    if docs.is_dir():
        targets.extend(docs.rglob("*.md"))

    root_readme = REPO_ROOT / "README.md"
    if root_readme.is_file():
        targets.append(root_readme)

    return sorted(set(targets))


@pytest.mark.parametrize("pattern,label", [
    (FOUNDER_FIRST_NAME, "founder first name 'Enes'"),
    (FOUNDER_USERNAME, "founder Unix username 'eneseserkan'"),
])
def test_no_founder_pii_in_committed_surface(pattern: re.Pattern[str], label: str) -> None:
    """No file in the customer-visible surface area mentions the founder.

    Failure prints the offenders so the next worker can clean them up
    without re-running grep manually.
    """
    offenders: list[tuple[str, int, str]] = []
    for path in _iter_scoped_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(REPO_ROOT)
                offenders.append((str(rel), line_no, line.strip()))

    assert not offenders, (
        f"PII leak: {label} found in {len(offenders)} place(s):\n"
        + "\n".join(f"  {p}:{n}: {snippet}" for p, n, snippet in offenders[:25])
    )


# Internal-infrastructure references that must not appear in customer-visible
# files: our private memory store, the founder's home path, and the separate
# orchestrator ("SERVER") working tree. These leak ops internals even when the
# literal name doesn't appear (e.g. ".claude/projects/.../memory/...").
_INTERNAL_INFRA = re.compile(
    r"\.claude/projects|/Users/eneseserkan|Automatia BCN/SERVER|kendi sistemimiz",
)


def _customer_visible_files() -> list[Path]:
    files = _iter_scoped_files()
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.is_file():
        files.append(claude_md)
    return sorted(set(files))


def test_no_internal_infra_refs_in_customer_surface() -> None:
    """Customer-visible files (panel, docs, README, CLAUDE.md) must not leak
    internal infra paths (private memory store, home path, the SERVER tree)."""
    offenders: list[tuple[str, int, str]] = []
    for path in _customer_visible_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _INTERNAL_INFRA.search(line):
                offenders.append(
                    (str(path.relative_to(REPO_ROOT)), line_no, line.strip())
                )
    assert not offenders, (
        f"internal-infra leak in {len(offenders)} place(s):\n"
        + "\n".join(f"  {p}:{n}: {s}" for p, n, s in offenders[:25])
    )


def test_test_029_uses_dynamic_repo_root() -> None:
    """Regression: GDPR test must not hardcode ``/Users/eneseserkan/...``.

    The original suite used absolute paths that broke on CI runners and
    other developers' workstations. Brief R1 §9 requires a dynamic
    ``Path(__file__).resolve().parents[3]`` resolver instead.
    """
    test_file = REPO_ROOT / "core" / "backend" / "tests" / "test_029_gdpr_account.py"
    text = test_file.read_text(encoding="utf-8")
    assert "/Users/eneseserkan/" not in text, (
        "test_029_gdpr_account.py still hardcodes the founder's home path. "
        "Use REPO_ROOT = Path(__file__).resolve().parents[3] instead."
    )
    assert "REPO_ROOT" in text, "test_029 must declare a REPO_ROOT helper."
