# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Diffs ABS computes itself, and why it stopped asking models for them.

Measured 2026-08-02 on the free tiers ABS routes to by default: three Composer
proposals in a row could not be applied, and all three refusals were correct.
The models wrote context lines that are not in the file, shifted indentation by
four spaces, and gave hunk headers whose counts did not match their bodies.
The prompt already specified the format, warned about indentation and carried a
worked example — prompt engineering had run out of room.

A diff computed from the bytes on disk cannot fail that way. These tests hold
that claim by running the real `git apply`, not by trusting the text to look
right.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from app.composer.from_content import (
    diff_from_new_content,
    edit_diff,
    read_text,
    relative_to,
)

ORIGINAL = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"


def _repo(tmp_path, text: str = ORIGINAL) -> str:
    (tmp_path / "util.py").write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return str(tmp_path)


def _applies(root: str, diff: str) -> tuple[bool, str]:
    """Ask git, not ourselves."""
    with open(os.path.join(root, "_p.diff"), "w", encoding="utf-8") as fh:
        fh.write(diff)
    r = subprocess.run(
        ["git", "apply", "--check", "_p.diff"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0, r.stderr.strip()


def test_a_diff_we_computed_applies(tmp_path):
    root = _repo(tmp_path)
    changed = ORIGINAL.replace(
        "def multiply(a, b):\n",
        'def multiply(a, b):\n    """Return the product of a and b."""\n',
    )
    diff, built = edit_diff(
        {"new_content": changed}, rel_path="util.py", abs_path=os.path.join(root, "util.py")
    )
    assert built is True
    ok, err = _applies(root, diff)
    assert ok, f"git refused a diff we computed from the file itself: {err}"


def test_the_failure_the_models_actually_produced_is_still_refused(tmp_path):
    """The real diff from a live run on 08-02: indentation shifted, and a
    context line the file does not contain. Kept as a test so nobody 'fixes'
    the engine into accepting it."""
    root = _repo(tmp_path)
    model_diff = (
        "--- a/util.py\n"
        "+++ b/util.py\n"
        "@@ -1,6 +1,8 @@\n"
        "-def add(a, b):\n"
        "-    return a + b\n"
        "+def add(a: int, b: int) -> int:\n"
        "+    return a + b\n"
        " \n"
        "-    def multiply(a, b):\n"
        "-        return a * b\n"
        "+    def multiply(a: int, b: int) -> int:\n"
        "+        return a * b\n"
    )
    ok, _ = _applies(root, model_diff)
    assert ok is False, "this patch does not fit the file and must not apply"


def test_an_unchanged_file_produces_no_edit(tmp_path):
    root = _repo(tmp_path)
    diff, built = edit_diff(
        {"new_content": ORIGINAL}, rel_path="util.py", abs_path=os.path.join(root, "util.py")
    )
    assert built is True
    assert diff == "", "echoing the file back is not a change"


def test_a_dropped_trailing_newline_is_not_a_rewrite(tmp_path):
    """Models routinely drop the final newline. That is not an edit."""
    root = _repo(tmp_path)
    diff, _ = edit_diff(
        {"new_content": ORIGINAL.rstrip("\n")},
        rel_path="util.py",
        abs_path=os.path.join(root, "util.py"),
    )
    assert diff == ""


def test_a_file_we_cannot_read_is_never_diffed_against(tmp_path):
    """None is not "empty" — diffing against nothing would propose deleting
    every line of a file we simply failed to open."""
    missing = str(tmp_path / "nope.py")
    assert read_text(missing) is None
    assert diff_from_new_content("nope.py", None, "anything\n") == ""


def test_a_model_that_still_sends_a_diff_is_not_broken(tmp_path):
    """Other callers and older prompts exist; their path stays open."""
    diff, built = edit_diff(
        {"unified_diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"},
        rel_path="x",
        abs_path=str(tmp_path / "x"),
    )
    assert built is False
    assert "@@" in diff


@pytest.mark.parametrize(
    "root,path,expected",
    [
        ("/w", "/w/src/a.py", "src/a.py"),
        ("/w", "src/a.py", "src/a.py"),
    ],
)
def test_paths_travel_as_the_diff_headers_need_them(root, path, expected):
    assert relative_to(root, path) == expected
