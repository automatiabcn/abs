# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Is this shell command safe enough to run without asking?

The agent shell gate (app/agentic/policy.py) used to send *every* command to a
human — `ls` and `git status` cost the same interruption as `rm -rf`. Asking
about the harmless ones is not free: it trains the reader to click through the
one that matters (approval fatigue is a security failure, not just friction).

This narrows the ask to the commands that can actually cost something. It is an
*allowlist* for auto-run, not a denylist for gating: a command runs without a
prompt only when we can prove it is read-only, and everything we cannot prove
keeps the human approval it had before. So a new attack shape is never auto-run
by default — the worst case of a gap here is one extra approval, never one
fewer.

Read-only means, concretely, all four:
  * the program cannot mutate the filesystem, the network, or process state,
  * it cannot execute code the repository controls (no `npm test`, whose script
    a hostile repo writes; those belong in the network-blocked sandbox, not on
    the agent's own shell, which inherits the operator's environment),
  * it cannot read a path that looks like a credential (a printed secret lands
    in the model's context, and tool output is untrusted from there on),
  * it carries no shell metacharacter that could smuggle a second command
    (a redirection, a substitution, a pipe into a shell).

Anything else — including anything this classifier is unsure about — returns
"gate", which is the existing behaviour.
"""

from __future__ import annotations

import re
import shlex

Classification = str  # "auto" | "gate"

# Programs that only read. None of these can execute a script the repository
# defines, open a socket, or change a file. `sed`/`awk` are deliberately absent:
# both run arbitrary code (`sed e`, `awk 'system(...)'`).
_READ_ONLY: frozenset[str] = frozenset(
    {
        "ls", "pwd", "echo", "cat", "bat", "head", "tail", "wc", "nl",
        "grep", "egrep", "fgrep", "rg", "ag", "ack",
        "find", "fd", "tree", "stat", "file", "du", "df",
        "date", "cal", "which", "type", "whoami", "id", "hostname", "uname",
        "cksum", "md5", "md5sum", "shasum", "sha1sum", "sha256sum",
        "sort", "uniq", "cut", "column", "comm", "diff", "cmp",
        "basename", "dirname", "realpath", "readlink",
        "true", "false", "printf", "seq", "yes",
        # `env` is deliberately absent: bare `env` dumps the environment
        # (secrets and all) into the transcript, and `env FOO=x cmd` runs cmd.
        # Neither has a safe read-only form on the agent's own shell.
    }
)

# git subcommands that only read. Mutating ones (add, commit, push, reset,
# checkout, merge, rebase, clean, stash, config, init, clone, rm, mv, fetch,
# pull, tag -d, branch -d, remote add) are simply not in this set, so they gate.
_GIT_READ_SUB: frozenset[str] = frozenset(
    {
        "status", "diff", "log", "show", "rev-parse", "ls-files", "ls-tree",
        "cat-file", "rev-list", "describe", "blame", "shortlog", "reflog",
        "symbolic-ref", "name-rev", "whatchanged", "show-ref", "for-each-ref",
        "count-objects", "var", "help", "version",
    }
)

# Flags/subwords that turn an otherwise-read subcommand into a write. Presence
# of any of these in a git segment sends it to a human even if the subcommand
# looked safe (`git branch -D x`, `git tag -d v1`).
_GIT_MUTATING_TOKENS: frozenset[str] = frozenset(
    {
        "-d", "-D", "--delete", "-m", "-M", "--move", "--force", "-f",
        "--set-url", "--add", "--unset", "--edit", "-e", "--amend",
    }
)

# Some read-only programs grow teeth with the right flag: `find -exec` runs a
# command, `find -delete` removes files, `fd -x` executes, `sort -o` writes a
# file. The flag means different things per program (`grep -o` is only-matching
# and safe; `sort -o` is an output file and is not), so the danger is keyed by
# program, not global.
_DANGEROUS_ARGS_BY_PROG: dict[str, frozenset[str]] = {
    "find": frozenset(
        {"-exec", "-execdir", "-delete", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
    ),
    "fd": frozenset({"-x", "--exec", "-X", "--exec-batch"}),
    "sort": frozenset({"-o", "--output"}),
}

# Shell metacharacters that can hide a second command or write a file. A segment
# containing any of these is never auto-run.
_DANGEROUS_META = re.compile(r"[>`]|\$\(|<\(|>\(|\|\||&&|;")

# A command is split on these into segments; every segment must be safe.
_SEGMENT_SPLIT = re.compile(r"\||&&|;|\n")

# Paths that hold secrets. Printing one into the transcript is an exfiltration
# primitive once the model's context is considered untrusted.
_SECRET_PATH = re.compile(
    r"(?i)(\.env|\.pem|\.key|id_rsa|id_ed25519|id_ecdsa|\.p12|\.pfx|"
    r"credentials|\.netrc|\.aws|\.ssh|\.gnupg|secret|token|password|"
    r"keychain|\.htpasswd)"
)


def _segment_is_read_only(segment: str) -> bool:
    segment = segment.strip()
    if not segment:
        return True  # an empty segment (e.g. trailing pipe) is harmless on its own
    if _DANGEROUS_META.search(segment):
        return False
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return False  # unbalanced quotes → cannot reason → gate
    if not tokens:
        return False
    # A leading VAR=value assignment prefix is a mutation of the environment for
    # the command; treat the whole thing as not-provably-safe.
    prog = tokens[0]
    if "=" in prog and not prog.startswith("="):
        return False
    if prog not in _READ_ONLY and prog != "git":
        return False
    # No argument may name a secret-looking path — for any program, including
    # cat — nor a flag that turns this program into one that writes or executes.
    danger_args = _DANGEROUS_ARGS_BY_PROG.get(prog, frozenset())
    for tok in tokens[1:]:
        if _SECRET_PATH.search(tok):
            return False
        base = tok.split("=", 1)[0]
        if base in danger_args:
            return False
    if prog == "git":
        if len(tokens) < 2:
            return False
        sub = tokens[1]
        if sub not in _GIT_READ_SUB:
            return False
        for t in tokens[2:]:
            if t in _GIT_MUTATING_TOKENS or t.split("=", 1)[0] == "--output":
                return False
    return True


def classify_command(command: str) -> Classification:
    """"auto" if the command is provably read-only, else "gate".

    Provably read-only = every segment (split on pipes and command separators)
    is a read-only program with no secret-path argument and no metacharacter
    that could smuggle another command. Unsure is "gate", always.
    """
    if not command or not command.strip():
        return "gate"
    # A command-substitution or redirection anywhere is disqualifying up front,
    # before splitting, so a `;`-hidden `>` cannot slip through a segment seam.
    if _DANGEROUS_META.search(command):
        return "gate"
    segments = _SEGMENT_SPLIT.split(command)
    if all(_segment_is_read_only(seg) for seg in segments):
        return "auto"
    return "gate"
