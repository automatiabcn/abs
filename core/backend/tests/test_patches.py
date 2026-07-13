"""Patch engine — parse, score, preview, apply."""

from __future__ import annotations

from app.patches.engine import parse_diff, score_patch


def test_parse_diff_extracts_hunks():
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n-old line\n+new line\n common\n"
    hunks = parse_diff(diff)
    assert len(hunks) == 1
    h = hunks[0]
    assert h.old_start == 1
    assert h.new_start == 1
    assert h.adds == 1
    assert h.dels == 1


def test_score_patch_minimal_hunk_high_score():
    diff = "@@ -1 +1 @@\n-old\n+new\n"
    r = score_patch(diff)
    assert r["score"] >= 7.0
    assert r["hunk_count"] == 1


def test_score_patch_big_hunk_lowers_score():
    # 100-line add block → penalty
    add_lines = "\n".join(f"+added {i}" for i in range(100))
    diff = "@@ -1,1 +1,100 @@\n common\n" + add_lines + "\n"
    r = score_patch(diff)
    assert r["max_hunk_size"] >= 80
    assert r["score"] <= 8.0


def test_score_patch_invalid_returns_zero():
    r = score_patch("this is not a diff")
    assert r["score"] == 0.0
    assert r["hunk_count"] == 0
