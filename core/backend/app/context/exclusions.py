# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Files and lines that must not be sent to a model as project context.

The product's sovereignty line is "only the context you approve reaches the
model". On 2026-08-18 an audit asked the chat, in a project whose
`.gitignore` listed `secrets.yaml` and `local/`, which Stripe key it used —
and the answer quoted it, because Chat and Composer walked the tree with a
suffix filter and nothing else. RAG had a secret-name denylist since June;
neither of the other two context builders used it. One module now, three
callers.

Three layers, each cheap and local:

1. **Ignore files.** `.gitignore` (root and nested) and `.absignore` (same
   syntax; ours, for "this may be tracked but do not show it to a model").
   What the developer told git to forget, the model does not get to see.
2. **Secret-shaped names.** `.env*`, `*secret*`, `*credential*`, key/cert
   suffixes, service-account and cloud-SDK JSON, ssh material — the RAG list
   plus what a real repo carries.
3. **Secret-shaped content.** Provider keys, cloud access keys, private-key
   blocks: redacted in place, the rest of the file still travels. A config
   file is useful context; the token in line 12 is not.

Everything here is deterministic and offline. Failing to read an ignore file
is not a reason to send more — it degrades to layers 2 and 3, never to
nothing.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:  # pathspec is in the venv; the fallback keeps air-gapped installs honest
    import pathspec as _pathspec
except Exception:  # noqa: BLE001
    _pathspec = None

IGNORE_FILES = (".gitignore", ".absignore")

# Layer 2 — names. Matched against the basename (fnmatch, case-insensitive)
# and, for the path forms, against the workspace-relative path.
SECRET_BASENAMES: Tuple[str, ...] = (
    ".env", ".env.*", "*.env",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.age",
    "*.kdbx", "*.gpg", "*.asc",
    "id_rsa", "id_rsa.pub", "id_ed25519", "id_ed25519.pub", "id_ecdsa", "id_dsa",
    "known_hosts", "authorized_keys",
    "*service*account*.json", "*serviceaccount*.json", "*-sa.json", "sa.json",
    "*firebase*adminsdk*.json", "*adminsdk*.json",
    "*.tfstate", "*.tfstate.backup", "terraform.tfvars",
    "*.db", "*.sqlite", "*.sqlite3",
    "admin_credentials.json", "demo_license.jwt", "license.jwt",
    "npmrc", ".npmrc", ".pypirc", ".netrc", "_netrc", ".git-credentials",
    "htpasswd", ".htpasswd", "shadow",
)
# "secret"/"credential" in the NAME is decisive for data files (secrets.yaml,
# credentials.json) and not for source (secrets_loader.py, credentials.ts are
# code about secrets, and the model may need to edit them). Source files rely
# on layer 3 instead.
SECRET_WORD_BASENAMES: Tuple[str, ...] = (
    "*secret*", "*credential*",
)
DATA_SUFFIXES: Tuple[str, ...] = (
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".xml", ".txt", ".env", ".csv", ".tfvars", "",
)
SECRET_PATH_PARTS: Tuple[str, ...] = (
    ".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config/gcloud", ".azure",
    "vault-key",
)

# Layer 3 — content. Conservative: long random-looking tokens behind a known
# prefix, and PEM blocks. False positives cost one line of context.
_SECRET_LINE = re.compile(
    r"("
    r"sk-[A-Za-z0-9_-]{16,}"                     # OpenAI/Anthropic/Stripe-style
    r"|sk_(live|test)_[A-Za-z0-9_-]{8,}"         # Stripe
    r"|rk_(live|test)_[A-Za-z0-9_-]{8,}"
    r"|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{16,}"
    r"|AKIA[0-9A-Z]{12,}"                        # AWS access key id
    r"|ASIA[0-9A-Z]{12,}"
    r"|AIza[0-9A-Za-z_-]{30,}"                   # Google API key
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"             # Slack
    r"|gsk_[A-Za-z0-9]{20,}"                     # Groq
    r"|csk-[A-Za-z0-9]{20,}"                     # Cerebras
    r"|hf_[A-Za-z0-9]{20,}"                      # HuggingFace
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"  # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r")"
)
_PEM_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
REDACTED = "[redacted by ABS: looks like a secret]"


def _norm(rel: str) -> str:
    rel = rel.replace(os.sep, "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel.lstrip("/")


def is_secret_path(rel: str) -> bool:
    """Layer 2: does the path LOOK like a credential file? Basename patterns
    plus a few directory names nobody wants in a prompt."""
    rel_n = _norm(rel)
    base = os.path.basename(rel_n).lower()
    for pat in SECRET_BASENAMES:
        if fnmatch.fnmatchcase(base, pat.lower()):
            return True
    suffix = os.path.splitext(base)[1]
    if suffix in DATA_SUFFIXES:
        for pat in SECRET_WORD_BASENAMES:
            if fnmatch.fnmatchcase(base, pat.lower()):
                return True
    parts = rel_n.lower().split("/")
    for part in SECRET_PATH_PARTS:
        segs = part.split("/")
        n = len(segs)
        for i in range(0, len(parts) - n + 1):
            if parts[i : i + n] == segs:
                return True
    return False


class IgnoreMatcher:
    """gitignore semantics for a workspace: root + nested ignore files, both
    `.gitignore` and `.absignore`. Uses pathspec when present; otherwise a
    fnmatch approximation that handles the common shapes (`dir/`, `*.ext`,
    `/anchored`, `!negation`)."""

    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        # (dir_rel, spec) — a nested ignore file only governs its subtree.
        self._specs: List[Tuple[str, object]] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Do not descend into things that are always excluded anyway.
            dirnames[:] = [
                d for d in dirnames
                if d not in ("node_modules", ".git", ".venv", "venv", "__pycache__")
            ]
            for name in IGNORE_FILES:
                if name in filenames:
                    p = os.path.join(dirpath, name)
                    try:
                        with open(p, encoding="utf-8", errors="ignore") as fh:
                            lines = fh.read().splitlines()
                    except OSError:
                        continue
                    rel_dir = _norm(os.path.relpath(dirpath, self.root))
                    rel_dir = "" if rel_dir == "." else rel_dir
                    self._specs.append((rel_dir, self._compile(lines)))

    @staticmethod
    def _compile(lines: Sequence[str]) -> object:
        if _pathspec is not None:
            try:
                return _pathspec.GitIgnoreSpec.from_lines(lines)
            except Exception:  # noqa: BLE001 — fall through to the approximation
                pass
        rules = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            neg = line.startswith("!")
            if neg:
                line = line[1:]
            anchored = line.startswith("/")
            line = line.lstrip("/")
            dir_only = line.endswith("/")
            line = line.rstrip("/")
            rules.append((neg, anchored, dir_only, line))
        return rules

    @staticmethod
    def _fnmatch_rules(rules: List[Tuple[bool, bool, bool, str]], rel: str, is_dir: bool) -> bool:
        ignored = False
        segs = rel.split("/")
        for neg, anchored, dir_only, pat in rules:
            hit = False
            if "/" in pat or anchored:
                hit = fnmatch.fnmatchcase(rel, pat) or fnmatch.fnmatchcase(rel, pat + "/*")
            else:
                # Unanchored: any path segment (or a prefix directory) may match.
                for i in range(len(segs)):
                    if fnmatch.fnmatchcase(segs[i], pat):
                        if dir_only and i == len(segs) - 1 and not is_dir:
                            continue
                        hit = True
                        break
            if hit:
                ignored = not neg
        return ignored

    def is_ignored(self, rel: str, *, is_dir: bool = False) -> bool:
        self._load()
        rel_n = _norm(rel)
        for rel_dir, spec in self._specs:
            if rel_dir:
                if not (rel_n == rel_dir or rel_n.startswith(rel_dir + "/")):
                    continue
                local = rel_n[len(rel_dir) + 1 :] if rel_n != rel_dir else ""
                if not local:
                    continue
            else:
                local = rel_n
            probe = local + "/" if is_dir else local
            if _pathspec is not None and not isinstance(spec, list):
                if spec.match_file(probe):  # type: ignore[attr-defined]
                    return True
            elif isinstance(spec, list):
                if self._fnmatch_rules(spec, local, is_dir):
                    return True
        return False


def excluded_reason(rel: str, matcher: Optional[IgnoreMatcher]) -> Optional[str]:
    """Why a workspace-relative path must not be sent — or None."""
    if is_secret_path(rel):
        return "looks like a credential file"
    if matcher is not None:
        try:
            if matcher.is_ignored(rel):
                return "ignored by .gitignore/.absignore"
        except Exception as exc:  # noqa: BLE001 — a broken ignore file widens nothing
            logger.debug("ignore match failed for %s: %s", rel, exc)
    return None


def filter_paths(root: str, rels: Iterable[str]) -> List[str]:
    """Drop every path that must not become model context."""
    matcher = IgnoreMatcher(root)
    return [r for r in rels if excluded_reason(r, matcher) is None]


def redact_secrets(text: str) -> Tuple[str, int]:
    """Layer 3: replace secret-shaped tokens; return (text, how_many)."""
    if not text:
        return text, 0
    n = 0
    text, k = _PEM_BLOCK.subn(REDACTED, text)
    n += k
    text, k = _SECRET_LINE.subn(REDACTED, text)
    n += k
    return text, n
