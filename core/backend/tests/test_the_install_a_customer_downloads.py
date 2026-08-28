# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The archive handed out by /download has to install.

Found 2026-08-03 by extracting it and running it the way a stranger would.
Four defects, none of which any test could have seen, because the suite checks
the source and a customer runs the artefact:

  1. `Caddyfile.customer` read `{$ABS_PUBLIC_HOSTNAME}` — a name nothing sets.
     Not `.env.example`, not the compose file; it survived here and in compose
     *comments*. An unset variable leaves the site block without a key, and a
     keyless block is how Caddy spells "global options", so it rejected the
     config and crash-looped. Every service healthy, front door dead.
  2. `install.sh` printed "ABS Studio server is up" and exited 0 while that was
     happening. The installer's claim was not connected to anything.
  3. The compose refuses to start without `ABS_DB_PASSWORD`, and
     `.env.example` did not mention it. A customer following the README to the
     letter met "required variable ABS_DB_PASSWORD is missing a value".
  4. The archive named 1.0.4 installed whatever `latest` pointed at.

The shape they share: the pieces were each fine and disagreed with each other.
So these tests check agreement between files rather than the contents of any
one of them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra"
CADDYFILE = INFRA / "Caddyfile.customer"
COMPOSE = INFRA / "docker-compose.customer.yml"
ENV_EXAMPLE = INFRA / ".env.example"
BUILDER = ROOT / "scripts" / "build_server_archive.sh"

pytestmark = pytest.mark.skipif(not INFRA.exists(), reason="infra not checked out")

# `{$NAME}` and `{$NAME:default}`. A default makes the variable optional, so
# only the bare form has to be provided by the customer's .env.
_READ = re.compile(r"\{\$([A-Z_][A-Z0-9_]*)(:[^}]*)?\}")


def _env_example_names() -> set[str]:
    names = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.add(line.split("=", 1)[0])
    return names


def test_the_proxy_reads_only_names_the_customer_env_defines():
    """The defect that took the front door down."""
    provided = _env_example_names()
    missing = []
    for match in _READ.finditer(CADDYFILE.read_text(encoding="utf-8")):
        name, default = match.group(1), match.group(2)
        if default is None and name not in provided:
            missing.append(name)
    assert missing == [], (
        "the reverse proxy reads variables nothing sets, which makes its site "
        "block keyless and crash-loops it: " + ", ".join(sorted(set(missing)))
    )


def test_every_variable_the_compose_requires_is_one_the_installer_supplies():
    """`${NAME:?...}` means compose refuses to start without it.

    Such a variable has to come from somewhere the customer does not have to
    know about — either `.env.example` ships it, or `install.sh` generates it.
    Leaving it to a README instruction is what produced defect 3.
    """
    required = set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*):?\?", COMPOSE.read_text(encoding="utf-8")))
    if not required:
        pytest.skip("nothing is declared mandatory")

    provided = _env_example_names()
    builder = BUILDER.read_text(encoding="utf-8") if BUILDER.exists() else ""
    unmet = [name for name in required if name not in provided and name not in builder]
    assert unmet == [], (
        "the compose will not start without these, and neither .env.example nor "
        "the installer provides them: " + ", ".join(sorted(unmet))
    )


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_the_installer_checks_before_it_claims_the_server_is_up():
    """Defect 2: a success message with nothing behind it.

    Pinned by behaviour rather than wording — the installer has to make a
    request to the address it is about to advertise.
    """
    text = BUILDER.read_text(encoding="utf-8")
    # Anchor on the line that actually announces it. Matching the bare phrase
    # found this file's own comment about the defect first, and passed a
    # version of the installer that had no check at all.
    announcement = re.search(r'^\s*echo "ABS Studio server is up\.', text, re.M)
    assert announcement, "the installer no longer announces success in a form this can check"
    before = text[: announcement.start()]
    assert "curl" in before, (
        "install.sh announces success without asking the front door whether it "
        "is answering; that is exactly what it did while Caddy crash-looped"
    )


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_the_archive_does_not_ship_our_own_deploy_scripts():
    """`infra/scripts` mixes what the container needs with what we run.

    A wildcard copy would hand a customer deploy_hetzner.sh — our hosts, our
    paths, our habits.
    """
    text = BUILDER.read_text(encoding="utf-8")
    copied = text[text.index('mkdir -p "$PKG/scripts"') :]
    for ours in ("deploy_hetzner.sh", "deploy_digisfer.sh", "setup_stripe_products.py"):
        assert ours not in copied, f"the customer archive would contain {ours}"
    assert "cp -R" not in copied.split("done")[0], (
        "scripts are copied by name on purpose; a recursive copy would sweep "
        "our deploy scripts in the moment somebody adds one"
    )


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_the_archive_installs_a_known_version():
    """Defect 4: the name on the tin meant nothing."""
    assert "ABS_VERSION=" in BUILDER.read_text(encoding="utf-8"), (
        "the compose defaults ABS_VERSION to `latest`, so an archive that does "
        "not pin it installs a different build depending on the day"
    )


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_the_installer_does_not_try_to_build_from_source():
    """`infra/install.sh` runs `docker compose build backend`.

    That is ours: it needs the source tree. A customer has an archive and
    published images, so a build step would fail on the first line that
    mattered.
    """
    text = BUILDER.read_text(encoding="utf-8")
    installer = text[text.index("INSTALL'") : text.index("\nINSTALL")]
    assert "compose build" not in installer, (
        "the customer installer tries to build an image from source it does "
        "not have"
    )


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_publishing_writes_a_signed_update_manifest():
    """A customer's server checks for updates every six hours and always failed.

    `app/update/manifest.py` has fetched, cached and compared versions since it
    was written; the file it reads has never existed. The URL returned the 404
    page, so the check failed silently and nobody was ever told a release
    happened.

    Two things had to be true for the fix to be worth anything, and only one of
    them was obvious:

    - the manifest is generated by the publish step, not written by hand, so it
      cannot claim a version that was never published; and
    - it is signed. The verifier is fail-closed — an unsigned manifest is
      treated as hostile, because a manifest is a machine telling a customer's
      server what to install. The first version of this step published an
      unsigned file, and the product's own verifier answered "signature
      missing — refused", which is fail-closed working exactly as intended
      against us.
    """
    text = BUILDER.read_text(encoding="utf-8")
    publish = text[text.index("--publish") :]

    assert "manifest.json" in publish, "publishing does not produce an update manifest"
    assert "current_version" in publish, "the manifest omits the field update_state reads"
    assert "manifest.json.sig" in publish, "the manifest is published unsigned"
    assert "abs-manifest-signing-private.pem" in publish, (
        "the manifest is not signed with the release key"
    )
    # The key stays where it is. Signing over ssh means the bytes travel to the
    # key; copying the key here would put a release-signing secret on a laptop.
    assert "ssh ai-pc" in publish, "signing does not happen where the key lives"


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_an_unsignable_manifest_stops_the_publish():
    """Publishing it unsigned is worse than not publishing it.

    Every customer's check would refuse the file, so the update would look
    broken everywhere rather than simply absent.
    """
    text = BUILDER.read_text(encoding="utf-8")
    publish = text[text.index("--publish") :]
    # Bounded by the upload that follows it. A window of "the next 800
    # characters" swept in the manifest-URL check's own `exit 1` and passed
    # with the signing failure ignored — the third guard today that looked
    # right and was measuring something else.
    start = publish.index("openssl dgst")
    end = publish.index("scp -q", start)
    sign_block = publish[start:end]
    assert "exit 1" in sign_block, "a failed signature does not stop the publish"


@pytest.mark.skipif(not BUILDER.exists(), reason="archive builder not present")
def test_the_install_guide_describes_the_installer_we_ship():
    """The page the licence email sends people to has to match the script.

    Nothing connected them, so improving the installer silently made the guide
    wrong. On 2026-08-04 it told a customer to `cd abs-server` — the archive
    extracts to a versioned directory, so the second line of the first
    instruction failed — and called the panel http://localhost:8000, which is
    the address the *editor* uses. Two wrong facts in four lines, both
    introduced by me the same day, in a different file.
    """
    guide = ROOT / "core" / "landing" / "app" / "docs" / "install" / "page.tsx"
    if not guide.is_file():
        pytest.skip("landing not checked out")

    text = guide.read_text(encoding="utf-8")
    builder = BUILDER.read_text(encoding="utf-8")

    # The archive is named with its version, so the directory is too.
    assert "cd abs-server\\n" not in text, (
        "the guide tells the customer to cd into a directory the archive does "
        "not create — it unpacks to abs-server-<version>"
    )

    # The setting the guide names has to be the one the extension contributes.
    manifest = ROOT.parent / "abs-editor" / "extensions" / "abs-ai" / "package.json"
    if manifest.is_file():
        import json

        contributed = json.loads(manifest.read_text(encoding="utf-8"))
        props = (
            contributed.get("contributes", {}).get("configuration", {}).get("properties", {})
        )
        assert "abs.serverUrl" in props, "the editor no longer contributes abs.serverUrl"
        assert "abs.serverUrl" in text, (
            "the guide does not name the setting a customer actually has to set"
        )

    # The installer writes the editor's settings; a guide that omits it sends
    # people to do work that was already done for them.
    if "settings.json" in builder:
        lowered = text.lower()
        assert "already pointed the editor" in lowered or "settings" in lowered, (
            "the installer configures the editor and the guide does not say so"
        )


def test_installer_does_not_swap_the_image_version_on_arm():
    """On a machine with no build for the pinned version the installer used to
    say "using latest instead" and run a different image version with an
    archive built for another — the mismatch /download names as the most
    common reason an install does not connect (audit #34, 2026-08-28). It
    must stop and say which versions have a build, not mix."""
    src = BUILDER.read_text(encoding="utf-8")
    assert "using latest instead" not in src
    branch = src[src.index('have no $PLATFORM build') :]
    assert "exit 1" in branch[: branch.index("fi\nfi")], "the no-build branch must stop the install"
    assert "set_env ABS_VERSION latest" not in branch[: branch.index("fi\nfi")]
