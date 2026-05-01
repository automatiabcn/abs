"""Patch engine — unified diff parse, preview, apply, score.

SERVER patch_engine.py'nin MVP portu:
  - parse_diff(): @@-headerlı hunk'ları listele
  - preview_patch(): subprocess `patch --dry-run` (macos/linux)
  - apply_patch(): atomic write + backup
  - score_patch(): minimalism + hunk konsantrasyonu 0-10
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
        return sum(1 for l in self.lines if l.op == "+")

    @property
    def dels(self) -> int:
        return sum(1 for l in self.lines if l.op == "-")


def parse_diff(text: str) -> List[Hunk]:
    """Unified diff → Hunk listesi. Başarısızsa boş."""
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
    """`patch --dry-run` ile önizleme. {success, reason} döner."""
    target = Path(file_path)
    if not target.is_file():
        return {"success": False, "reason": f"dosya yok: {file_path}"}

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
        # `patch` binary yok (Docker slim) → yapılandırılabilir; graceful degrade
        return {
            "success": False,
            "reason": "`patch` binary yok (apt-get install patch)",
        }
    except Exception as exc:
        return {"success": False, "reason": str(exc)[:200]}
    finally:
        try:
            Path(patch_path).unlink(missing_ok=True)
        except Exception:
            pass


def apply_patch(file_path: str, diff_text: str, backup: bool = True) -> dict:
    """Atomic write + opsiyonel backup. {success, reason, backup_path} döner."""
    target = Path(file_path)
    if not target.is_file():
        return {"success": False, "reason": f"dosya yok: {file_path}"}

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
        return {"success": True, "backup_path": backup_path, "stdout": result.stdout[:300]}
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
    """Diff'i minimalism + hunk konsantrasyonu + boyut ile skorla (0-10)."""
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

    # Skor kuralları (basit):
    # - 1-3 hunk + minimal_ratio > 0.3 + max_hunk < 40 → 8-10
    # - 4-6 hunk → 6-7
    # - 7+ hunk veya max_hunk > 80 → 4-5
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
        teaching.append(f"{hunk_count} hunk — dağınık patch; bölerek küçült.")
    if max_hunk_size > 80:
        teaching.append(f"En büyük hunk {max_hunk_size} satır — fonksiyon ayır.")
    if minimal_ratio < 0.2:
        teaching.append("Context oranı yüksek — hunk'lar genişletilmiş; daraltılabilir.")
    if not teaching:
        teaching.append("Dar ve konsantre patch — senior signature'a uygun.")

    return {
        "score": round(score, 1),
        "hunk_count": hunk_count,
        "minimal_ratio": round(minimal_ratio, 2),
        "max_hunk_size": max_hunk_size,
        "teaching": " ".join(teaching),
    }
