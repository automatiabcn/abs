"""010 — AST-aware RAG chunker.

Python: top-level function/class boundary.
Markdown: heading-based (#..######).
Diğer: char-fallback _CHAR_FALLBACK boyutunda.

`chunk_for_path(path, text, strategy)` her durumda iter[(idx, chunk)] döner.
strategy="char" → her uzantı için char-split. "semantic" (default) → AST-aware.

Exception-free contract: invalid Python parse hatası char-fallback'e düşer.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, Tuple

_CHAR_FALLBACK = 1500
_MAX_CHUNK_BYTES = 8000  # tek dev fonksiyon edge case → re-split


def chunk_chars(text: str, size: int = _CHAR_FALLBACK) -> Iterable[Tuple[int, str]]:
    if not text:
        return
    for i, start in enumerate(range(0, len(text), size)):
        piece = text[start : start + size]
        if piece:
            yield i, piece


def _explode_oversized(text: str, base_idx: int) -> Iterable[Tuple[int, str]]:
    """Tek chunk _MAX_CHUNK_BYTES'ı aşarsa char-split."""
    if len(text) <= _MAX_CHUNK_BYTES:
        yield base_idx, text
        return
    for sub_idx, start in enumerate(range(0, len(text), _CHAR_FALLBACK)):
        sub = text[start : start + _CHAR_FALLBACK]
        if sub.strip():
            yield base_idx + sub_idx, sub


def chunk_python(text: str) -> Iterable[Tuple[int, str]]:
    """Top-level def/class boundary'lerinde böl. Boundary öncesi 'preamble' chunk."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        yield from chunk_chars(text)
        return
    boundaries = sorted(
        n.lineno
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    if not boundaries:
        yield from chunk_chars(text)
        return
    lines = text.splitlines(keepends=True)
    boundaries = [1] + boundaries + [len(lines) + 1]
    idx = 0
    for start, end in zip(boundaries, boundaries[1:]):
        chunk = "".join(lines[start - 1 : end - 1]).strip()
        if not chunk:
            continue
        for sub_idx, piece in _explode_oversized(chunk, idx):
            yield sub_idx, piece
            idx = sub_idx + 1


_MD_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


def chunk_markdown(text: str) -> Iterable[Tuple[int, str]]:
    """Heading bazlı bölme. Heading yoksa char-fallback."""
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        yield from chunk_chars(text)
        return
    boundaries = [m.start() for m in matches] + [len(text)]
    idx = 0
    if boundaries[0] > 0:
        preamble = text[: boundaries[0]].strip()
        if preamble:
            for sub_idx, piece in _explode_oversized(preamble, idx):
                yield sub_idx, piece
                idx = sub_idx + 1
    for start, end in zip(boundaries, boundaries[1:]):
        section = text[start:end].strip()
        if not section:
            continue
        for sub_idx, piece in _explode_oversized(section, idx):
            yield sub_idx, piece
            idx = sub_idx + 1


def chunk_for_path(
    path: Path, text: str, strategy: str = "semantic"
) -> Iterable[Tuple[int, str]]:
    """Strategy + uzantıya göre chunker'a yönlendir. Exception fırlatmaz."""
    if strategy == "char":
        yield from chunk_chars(text)
        return
    suf = path.suffix.lower()
    try:
        if suf == ".py":
            yield from chunk_python(text)
        elif suf in (".md", ".mdx"):
            yield from chunk_markdown(text)
        else:
            yield from chunk_chars(text)
    except Exception:  # pragma: no cover — son kale
        yield from chunk_chars(text)
