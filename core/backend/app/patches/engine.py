# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Patch engine — parse, preview, apply and score unified diffs.

- parse_diff():    list the @@-headed hunks
- preview_patch(): `patch --dry-run`, so nothing is written to check a patch
- apply_patch():   atomic write, with a backup by default
- score_patch():   0-10 on minimalism and how concentrated the hunks are
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HunkLine:
    op: str  # " " / "+" / "-"
    text: str


@dataclass
class Hunk:
    old_start: int
    new_start: int
    section: str = ""
    lines: List[HunkLine] = field(default_factory=list)

    @property
    def adds(self) -> int:
        return sum(1 for line in self.lines if line.op == "+")

    @property
    def dels(self) -> int:
        return sum(1 for line in self.lines if line.op == "-")


def parse_diff(text: str) -> List[Hunk]:
    """Unified diff → hunks. Unparseable input yields an empty list, not an error."""
    hunks: List[Hunk] = []
    current: Optional[Hunk] = None
    header_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")
    for raw in text.splitlines():
        m = header_re.match(raw)
        if m:
            if current:
                hunks.append(current)
            current = Hunk(
                old_start=int(m.group(1)),
                new_start=int(m.group(2)),
                section=m.group(3).strip(),
            )
            continue
        if current is None:
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith(" "):
            current.lines.append(HunkLine(" ", raw[1:]))
        elif raw.startswith("+"):
            current.lines.append(HunkLine("+", raw[1:]))
        elif raw.startswith("-"):
            current.lines.append(HunkLine("-", raw[1:]))
    if current:
        hunks.append(current)
    return hunks


def preview_patch(file_path: str, diff_text: str) -> dict:
    """Dry-run the patch without touching the file. Returns {success, reason}."""
    target = Path(file_path)
    if not target.is_file():
        return {"success": False, "reason": f"no such file: {file_path}"}

    try:
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as tmp:
            tmp.write(diff_text)
            patch_path = tmp.name
        result = subprocess.run(
            ["patch", "--dry-run", "-p1", "-i", patch_path, str(target)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ok = result.returncode == 0
        return {
            "success": ok,
            "reason": "" if ok else result.stderr[:200] or result.stdout[:200],
            "stdout": result.stdout[:500],
        }
    except FileNotFoundError:
        # Slim images ship without `patch` — report it instead of crashing.
        return {
            "success": False,
            "reason": "`patch` binary not available (apt-get install patch)",
        }
    except Exception as exc:
        return {"success": False, "reason": str(exc)[:200]}
    finally:
        try:
            Path(patch_path).unlink(missing_ok=True)
        except Exception:
            pass


def apply_patch(file_path: str, diff_text: str, backup: bool = True) -> dict:
    """Apply the patch with an atomic write. Returns {success, reason, backup_path}."""
    target = Path(file_path)
    if not target.is_file():
        return {"success": False, "reason": f"no such file: {file_path}"}

    backup_path: Optional[str] = None
    if backup:
        bp = target.with_suffix(target.suffix + ".bak")
        try:
            shutil.copy2(target, bp)
            backup_path = str(bp)
        except Exception as exc:
            return {"success": False, "reason": f"backup fail: {exc}"}

    try:
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as tmp:
            tmp.write(diff_text)
            patch_path = tmp.name

        result = subprocess.run(
            ["patch", "-p1", "-i", patch_path, str(target)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            # rollback
            if backup_path:
                shutil.copy2(backup_path, target)
            return {
                "success": False,
                "reason": result.stderr[:200] or result.stdout[:200],
                "backup_path": backup_path,
            }
        return {
            "success": True,
            "backup_path": backup_path,
            "stdout": result.stdout[:300],
        }
    except FileNotFoundError:
        return {"success": False, "reason": "`patch` binary yok"}
    except Exception as exc:
        if backup_path:
            try:
                shutil.copy2(backup_path, target)
            except Exception:
                pass
        return {"success": False, "reason": str(exc)[:200]}
    finally:
        try:
            Path(patch_path).unlink(missing_ok=True)
        except Exception:
            pass


def score_patch(diff_text: str) -> dict:
    """Score a diff 0-10 on minimalism, hunk concentration and size."""
    hunks = parse_diff(diff_text)
    if not hunks:
        return {
            "score": 0.0,
            "hunk_count": 0,
            "minimal_ratio": 0.0,
            "max_hunk_size": 0,
            "teaching": "No valid hunk found — check unified diff format.",
        }

    hunk_count = len(hunks)
    max_hunk_size = max(h.adds + h.dels for h in hunks)
    total_changes = sum(h.adds + h.dels for h in hunks)
    total_context = sum(len(h.lines) - (h.adds + h.dels) for h in hunks)
    minimal_ratio = total_changes / max(1, total_changes + total_context)

    # A good patch is small and concentrated: few hunks, little surrounding
    # context, no single sprawling hunk. Each of those failings costs points.
    score = 10.0
    if hunk_count > 3:
        score -= 1.5
    if hunk_count > 6:
        score -= 1.5
    if max_hunk_size > 40:
        score -= 1.0
    if max_hunk_size > 80:
        score -= 1.5
    if minimal_ratio < 0.2:
        score -= 1.0
    score = max(0.0, min(10.0, score))

    teaching = []
    if hunk_count > 6:
        teaching.append(
            f"{hunk_count} hunks — scattered patch; split it into smaller ones."
        )
    if max_hunk_size > 80:
        teaching.append(f"Largest hunk is {max_hunk_size} lines — extract a function.")
    if minimal_ratio < 0.2:
        teaching.append("Lots of context per change — the hunks can be tightened.")
    if not teaching:
        teaching.append("Narrow, concentrated patch.")

    return {
        "score": round(score, 1),
        "hunk_count": hunk_count,
        "minimal_ratio": round(minimal_ratio, 2),
        "max_hunk_size": max_hunk_size,
        "teaching": " ".join(teaching),
    }
