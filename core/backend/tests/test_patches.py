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


def test_dry_run_tolerates_trailing_blank_context_at_eof(tmp_path):
    """Live tour: groq ended the hunk with a blank context line past EOF —
    a trailing-newline artifact, not a real line. A byte-exact patch must not
    be rejected over it (and the editor's applier already tolerates it)."""
    f = _write(tmp_path, "util.py", "def helper():\n    return 1\n")
    diff = (
        "--- util.py\t2024-01-01 00:00:00.00\n"
        "+++ util.py\t2024-01-01 00:00:00.00\n"
        "@@ -1,5 +1,5 @@\n def helper():\n-    return 1\n+    return 2\n \n"
    )
    d = dry_run(str(f), diff, workspace_root=str(tmp_path))
    assert d.success, d.reason
    assert d.method == "inmemory"  # not the fuzzy git fallback
    r = apply(str(f), diff, workspace_root=str(tmp_path))
    assert r.success, r.reason
    assert f.read_text(encoding="utf-8") == "def helper():\n    return 2\n"


def test_appending_past_a_phantom_blank_separator_applies(tmp_path):
    """Live tour (07-31): asked to append a function, groq wrote the separator
    blank line as CONTEXT — it pictures the file ending with one — then put its
    `+` lines after it. The file has no such line, so the old block was one
    phantom line long and both proposals died with "does not apply". The model
    meant the blank line to be IN the new file; converting it to an insertion
    reproduces that intent exactly."""
    f = _write(tmp_path, "util.py", "def add(a, b):\n    return a + b\n")
    diff = (
        "@@ -1,5 +1,7 @@\n def add(a, b):\n     return a + b\n \n"
        "+def multiply(a, b):\n+    return a * b\n"
    )
    d = dry_run(str(f), diff, workspace_root=str(tmp_path))
    assert d.success, d.reason
    assert d.method == "inmemory"
    r = apply(str(f), diff, workspace_root=str(tmp_path))
    assert r.success, r.reason
    assert f.read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
    )


def test_a_pure_context_append_is_read_as_the_insertion_it_means(tmp_path):
    """Live tour (07-31), verbatim shape: asked to append, groq emitted the
    file it intends as PURE context — not one `+` in the hunk. The old block
    then runs two phantom lines past EOF and a strict engine refuses, while
    the judge, shown a no-op diff, scores the proposal 0. The prefix matches
    the file ending exactly at EOF, so the leftover context lines have nothing
    to match — they can only be insertions. The dry-run must also hand back
    the repaired text, because that is the change actually being approved."""
    f = _write(tmp_path, "util.py", "def add(a, b):\n    return a + b\n")
    live = (
        "@@ -1,5 +1,7 @@\n def add(a, b):\n     return a + b\n \n"
        " def multiply(a, b):\n     return a * b\n"
    )
    d = dry_run(str(f), live, workspace_root=str(tmp_path))
    assert d.success, d.reason
    assert d.method == "inmemory"
    assert "+def multiply(a, b):" in d.repaired_diff
    assert "+    return a * b" in d.repaired_diff
    r = apply(str(f), live, workspace_root=str(tmp_path))
    assert r.success, r.reason
    assert f.read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
    )


def test_a_deletion_past_eof_is_still_a_refusal(tmp_path):
    """The repair reads context past EOF as insertion; a DELETION past EOF is
    a claim about content that does not exist and must stay a refusal."""
    f = _write(tmp_path, "util.py", "def add(a, b):\n    return a + b\n")
    diff = (
        "@@ -1,3 +1,2 @@\n def add(a, b):\n     return a + b\n-    phantom\n"
    )
    assert not dry_run(str(f), diff, workspace_root=str(tmp_path)).success


def test_the_repaired_diff_reapplies_strictly(tmp_path):
    """What dry_run hands back must round-trip through a strict pass — the
    editor's own applier never saw the engine's repairs."""
    f = _write(tmp_path, "util.py", "def add(a, b):\n    return a + b\n")
    live = (
        "@@ -1,5 +1,7 @@\n def add(a, b):\n     return a + b\n \n"
        " def multiply(a, b):\n     return a * b\n"
    )
    d = dry_run(str(f), live, workspace_root=str(tmp_path))
    assert d.success and d.repaired_diff
    d2 = dry_run(str(f), d.repaired_diff, workspace_root=str(tmp_path))
    assert d2.success, d2.reason
    assert d2.preview == d.preview


def test_blank_context_inside_a_hunk_is_still_required(tmp_path):
    f = _write(tmp_path, "mid.txt", "a\nb\nc\n")
    diff = "@@ -1,3 +1,3 @@\n a\n \n-b\n+B\n"
    assert not dry_run(str(f), diff, workspace_root=str(tmp_path)).success


def test_applies_the_shape_the_live_model_emits(tmp_path):
    """Live tour, verbatim: groq wrote `- def helper():` — marker, courtesy
    space, then code — so every line carried a phantom indent and the strict
    pass matched nothing. The content is right; the engine must read it."""
    f = _write(tmp_path, "util.py", "def helper():\n    return 1\n")
    live = (
        "@@ -1,5 +1,5 @@\n- def helper():\n-     return 1\n"
        "+ def helper():\n+     return 2\n"
    )
    d = dry_run(str(f), live, workspace_root=str(tmp_path))
    assert d.success, d.reason
    assert d.method == "inmemory"
    r = apply(str(f), live, workspace_root=str(tmp_path))
    assert r.success, r.reason
    assert f.read_text(encoding="utf-8") == "def helper():\n    return 2\n"


def test_genuinely_indented_hunk_is_not_dedented(tmp_path):
    """The space repair must never fire on a correct diff: a hunk whose lines
    really are indented has to apply at its real indentation."""
    f = _write(tmp_path, "c.py", "class C:\n    def m(self):\n        return 1\n")
    good = (
        "@@ -1,3 +1,3 @@\n class C:\n     def m(self):\n"
        "-        return 1\n+        return 2\n"
    )
    assert dry_run(str(f), good, workspace_root=str(tmp_path)).success
    assert apply(str(f), good, workspace_root=str(tmp_path)).success
    assert f.read_text(encoding="utf-8") == (
        "class C:\n    def m(self):\n        return 2\n"
    )


def test_a_header_with_a_leading_space_is_still_a_header():
    """Models told "every line starts with exactly one marker character" apply
    that to the @@ line too. Measured live: " @@ -1,4 +1,4 @@" made the whole
    patch read as having no header, so nothing could be applied."""
    from app.patches.engine import parse_diff

    hunks = parse_diff(" @@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n")
    assert len(hunks) == 1
    assert hunks[0].old_start == 1


def test_a_context_line_is_not_mistaken_for_a_header():
    from app.patches.engine import parse_diff

    # A context line whose content merely mentions @@ must stay a context line.
    hunks = parse_diff("@@ -1,2 +1,2 @@\n print('@@ not a header')\n-a\n+b\n")
    assert len(hunks) == 1
    assert any("not a header" in line.text for line in hunks[0].lines)


def test_a_uniformly_shifted_hunk_is_read_back(tmp_path):
    """Shown a worked example, models line the markers up and push every line
    one column right: " -    return 1". Measured live — the hunk then read as
    context whose content merely began with a marker, and nothing applied."""
    from app.patches.engine import apply_patch, parse_diff

    shifted = "@@ -1,2 +1,2 @@\n def helper():\n -    return 1\n +    return 2\n"
    hunks = parse_diff(shifted)
    assert [line.op for line in hunks[0].lines] == [" ", "-", "+"]

    f = tmp_path / "util.py"
    f.write_text("def helper():\n    return 1\n", encoding="utf-8")
    apply_patch(str(f), shifted, workspace_root=str(tmp_path))
    assert "return 2" in f.read_text(encoding="utf-8")


def test_a_markdown_bullet_is_not_dedented():
    """Context lines that legitimately start with '-' must survive: such a hunk
    still carries its own real marker lines, which is what tells them apart."""
    from app.patches.engine import parse_diff

    diff = "@@ -1,3 +1,3 @@\n - first bullet\n-- old bullet\n+- new bullet\n"
    hunks = parse_diff(diff)
    ops = [line.op for line in hunks[0].lines]
    assert ops == [" ", "-", "+"]
    assert hunks[0].lines[0].text == "- first bullet"


def test_normalize_returns_the_diff_the_engine_would_apply():
    """Whatever the model wrote, one text goes to the judge, the panel and the
    applier. Handed the raw shifted diff, the judge could not read a single
    added line and scored a correct edit 0."""
    from app.patches.engine import normalize_diff

    shifted = " @@ -1,2 +1,2 @@\n def helper():\n -    return 1\n +    return 2\n"
    out = normalize_diff(shifted)
    assert out.startswith("@@ -1,2 +1,2 @@")
    assert "\n-    return 1" in out
    assert "\n+    return 2" in out


def test_normalize_leaves_unparseable_text_alone():
    from app.patches.engine import normalize_diff

    assert normalize_diff("not a diff") == "not a diff"
