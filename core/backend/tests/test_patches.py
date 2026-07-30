"""Patch engine — parse, score, preview, apply, sandbox, rollback."""

from __future__ import annotations

from app.patches.engine import (
    apply,
    dry_run,
    parse_diff,
    score_patch,
    validate,
)


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


# --- apply / dry-run --------------------------------------------------------

_ONE_LINE_DIFF = "@@ -1,3 +1,3 @@\n line1\n-line2\n+line2-changed\n line3\n"


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_apply_changes_file_and_backs_up(tmp_path):
    f = _write(tmp_path, "x.txt", "line1\nline2\nline3\n")
    r = apply(str(f), _ONE_LINE_DIFF, workspace_root=str(tmp_path))
    assert r.success, r.reason
    assert f.read_text() == "line1\nline2-changed\nline3\n"
    assert r.lines_added == 1 and r.lines_deleted == 1
    assert r.backup_path is not None


def test_dry_run_does_not_touch_file(tmp_path):
    f = _write(tmp_path, "x.txt", "line1\nline2\nline3\n")
    before = f.read_text()
    r = dry_run(str(f), _ONE_LINE_DIFF, workspace_root=str(tmp_path))
    assert r.success
    assert f.read_text() == before  # untouched


def test_apply_rolls_back_on_broken_python_ast(tmp_path):
    f = _write(tmp_path, "m.py", "def f():\n    return 1\n")
    broken = "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return (1\n"
    r = apply(str(f), broken, workspace_root=str(tmp_path))
    assert not r.success
    assert "rolled back" in r.reason.lower()
    assert f.read_text() == "def f():\n    return 1\n"  # restored


# --- workspace sandbox (the security boundary) ------------------------------

def test_sandbox_rejects_path_outside_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = _write(tmp_path, "outside.txt", "secret\n")
    v = validate(str(outside), _ONE_LINE_DIFF, workspace_root=str(ws))
    assert not v.valid
    assert v.stage == "sandbox"


def test_sandbox_rejects_dotdot_traversal(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write(tmp_path, "outside.txt", "secret\n")
    escape = str(ws / ".." / "outside.txt")
    v = validate(escape, _ONE_LINE_DIFF, workspace_root=str(ws))
    assert not v.valid
    assert v.stage == "sandbox"


def test_sandbox_allows_path_inside_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    inside = _write(ws, "in.txt", "line1\nline2\nline3\n")
    v = validate(str(inside), _ONE_LINE_DIFF, workspace_root=str(ws))
    assert v.valid, f"{v.stage}: {v.reason}"


def test_validate_requires_absolute_without_workspace():
    v = validate("relative/path.txt", _ONE_LINE_DIFF)
    assert not v.valid
    assert v.stage == "path"


# --- unique-match relocation (models mis-number @@ headers) ------------------


def test_dry_run_relocates_misnumbered_hunk(tmp_path):
    """The live Composer tour showed groq declaring `@@ -5` for a 2-line file;
    content-exact diffs must apply anyway (the editor's applier already does)."""
    f = _write(tmp_path, "util.py", "def helper():\n    return 1\n")
    bad_position = "@@ -5,2 +5,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    d = dry_run(str(f), bad_position, workspace_root=str(tmp_path))
    assert d.success, d.reason
    r = apply(str(f), bad_position, workspace_root=str(tmp_path))
    assert r.success, r.reason
    assert "return 2" in f.read_text(encoding="utf-8")


def test_dry_run_refuses_ambiguous_relocation(tmp_path):
    f = _write(tmp_path, "twice.txt", "x = 1\ny = 2\nx = 1\ny = 2\n")
    diff = "@@ -9,2 +9,2 @@\n x = 1\n-y = 2\n+y = 3\n"
    d = dry_run(str(f), diff, workspace_root=str(tmp_path))
    assert not d.success
    assert "ambiguous" in (d.reason or "")


def test_dry_run_refuses_when_content_matches_nowhere(tmp_path):
    f = _write(tmp_path, "x.txt", "line1\nline2\nline3\n")
    diff = "@@ -1,2 +1,2 @@\n line1\n-NOT-IN-FILE\n+new\n"
    d = dry_run(str(f), diff, workspace_root=str(tmp_path))
    assert not d.success
