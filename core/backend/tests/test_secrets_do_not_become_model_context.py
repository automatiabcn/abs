"""What the developer told git to forget, and what looks like a credential,
does not travel to a model as project context.

Audit 2026-08-18: in a workspace with `secrets.yaml` and `local/sa.json` both
in .gitignore, `cascade_ask("which stripe key…")` sent both to Cloudflare and
the answer quoted the keys. Composer's walker knew suffixes and nothing else;
RAG had a denylist since June that neither Chat nor Composer used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.composer import runtime
from app.context import exclusions as ex


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "cart.py").write_text("def total(items):\n    return sum(items)\n")
    (tmp_path / "shop" / "config.yaml").write_text(
        "stripe:\n  key: sk_live_ABCDEF1234567890XYZ\nregion: eu\n"
    )
    (tmp_path / "secrets.yaml").write_text("aws: AKIAFAKE1234567890\n")
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "sa.json").write_text('{"private_key": "-----BEGIN PRIVATE KEY-----\\nX\\n-----END PRIVATE KEY-----"}')
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.js").write_text("var x = 1;\n")
    (tmp_path / "notes.md").write_text("Roadmap\n")
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "big.json").write_text("{}\n")
    (tmp_path / ".gitignore").write_text("secrets.yaml\nlocal/\n")
    (tmp_path / ".absignore").write_text("gen/\n")
    return tmp_path


# --- layer 1: ignore files -------------------------------------------------

def test_gitignored_and_absignored_paths_are_not_listed(ws):
    files = runtime.workspace_files(str(ws))
    assert "shop/cart.py" in files
    assert "notes.md" in files
    assert "secrets.yaml" not in files
    assert "local/sa.json" not in files
    assert "gen/big.json" not in files


def test_nested_gitignore_governs_its_subtree(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / ".gitignore").write_text("*.local.py\n")
    (tmp_path / "a" / "x.local.py").write_text("x=1\n")
    (tmp_path / "a" / "y.py").write_text("y=1\n")
    (tmp_path / "z.local.py").write_text("z=1\n")
    files = runtime.workspace_files(str(tmp_path))
    assert "a/y.py" in files
    assert "a/x.local.py" not in files
    assert "z.local.py" in files  # the nested rule does not reach the root


def test_a_broken_ignore_file_widens_nothing(tmp_path, monkeypatch):
    (tmp_path / "ok.py").write_text("x=1\n")
    (tmp_path / ".gitignore").write_bytes(b"\xff\xfe[[[")
    files = runtime.workspace_files(str(tmp_path))
    assert files == ["ok.py"]


# --- layer 2: credential-shaped names --------------------------------------

@pytest.mark.parametrize(
    "rel",
    [
        ".env", ".env.local", "prod.env", "secrets.yaml", "credentials.json",
        "service-account.json", "firebase-adminsdk-x.json", "id_ed25519",
        "keys/server.pem", "cert.key", ".aws/credentials", "x/.ssh/config",
        "terraform.tfstate", "db.sqlite3", "local/sa.json",
    ],
)
def test_credential_shaped_paths_are_refused_by_name(rel):
    assert ex.is_secret_path(rel), rel


@pytest.mark.parametrize(
    "rel",
    ["shop/cart.py", "secrets_loader.py", "credentials.ts", "config.yaml",
     "README.md", "src/env.ts", "environment.py"],
)
def test_source_about_secrets_is_still_context(rel):
    """`secrets_loader.py` is code about secrets; the model may need to edit
    it. Only DATA files with the word are refused by name."""
    assert not ex.is_secret_path(rel), rel


def test_a_credential_file_is_dropped_even_when_handed_in_directly(ws):
    """A caller that builds its own listing cannot bypass the rules."""
    picked = runtime.relevant_files(
        str(ws), "which stripe key", ["secrets.yaml", "shop/cart.py", "local/sa.json"]
    )
    names = [rel for rel, _ in picked]
    assert names == ["shop/cart.py"]


# --- layer 3: content --------------------------------------------------------

def test_secret_tokens_are_redacted_and_the_file_still_travels(ws):
    picked = dict(runtime.relevant_files(str(ws), "stripe region", ["shop/config.yaml"]))
    body = picked["shop/config.yaml"]
    assert "sk_live_ABCDEF" not in body
    assert ex.REDACTED in body
    assert "region: eu" in body


@pytest.mark.parametrize(
    "text",
    [
        "key = 'sk-proj-abcdefghijklmnopqrstuv'",
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
        "token: ghp_abcdefghijklmnopqrstuvwxyz0123",
        "google: AIzaSyA-abcdefghijklmnopqrstuvwxyz0123456",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----",
        "jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop",
    ],
)
def test_known_secret_shapes_are_redacted(text):
    out, n = ex.redact_secrets(text)
    assert n >= 1
    assert ex.REDACTED in out


def test_ordinary_code_is_not_redacted():
    src = "def sk_helper():\n    return 'skate-park'\nAKIA = 'not a key'\n"
    out, n = ex.redact_secrets(src)
    assert n == 0 and out == src


def test_composer_refuses_to_write_the_marker_back(tmp_path):
    """The model saw a marker; writing it to disk would overwrite the token."""
    from app.composer import from_content

    f = tmp_path / "config.yaml"
    f.write_text("key: sk_live_ABCDEF1234567890XYZ\nregion: eu\n")
    raw = {"new_content": f"key: {ex.REDACTED}\nregion: us\n"}
    why = from_content.refusal(raw, rel_path="config.yaml", abs_path=str(f))
    assert why and "hid from the model" in why
    ok = {"new_content": "key: sk_live_ABCDEF1234567890XYZ\nregion: us\n"}
    assert from_content.refusal(ok, rel_path="config.yaml", abs_path=str(f)) is None


# --- RAG shares the rules ---------------------------------------------------

def test_rag_walker_skips_gitignored_and_secret_files(ws):
    from app.rag import indexer

    got = {str(p.relative_to(ws)) for p in indexer._walk_files(ws, [".py", ".yaml", ".json", ".md", ".js"])}
    assert "shop/cart.py" in got
    assert "secrets.yaml" not in got
    assert "local/sa.json" not in got
    assert "gen/big.json" not in got
    assert indexer._unsafe_index_path(ws / "shop" / "config.yaml") is None
    assert indexer._unsafe_index_path(Path("/x/service-account.json")) == "blocked_secret_shape"
