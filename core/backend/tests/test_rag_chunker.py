"""RAG semantic chunker tests (without Chroma)."""

from __future__ import annotations

from pathlib import Path

from app.rag.chunker import (
    chunk_chars,
    chunk_for_path,
    chunk_markdown,
    chunk_python,
)


def _collect(it):
    return list(it)


def test_python_chunks_split_at_function_boundary():
    src = '''"""Module preamble."""\nimport os\n\n\ndef alpha():\n    return 1\n\n\ndef beta():\n    return 2\n\n\nclass Gamma:\n    def m(self):\n        return 3\n'''
    chunks = _collect(chunk_python(src))
    assert len(chunks) == 4, (
        f"beklenen 4 (preamble + alpha + beta + Gamma), gelen {len(chunks)}"
    )
    bodies = [c for _, c in chunks]
    assert any("import os" in b for b in bodies)
    assert any("def alpha" in b for b in bodies)
    assert any("def beta" in b for b in bodies)
    assert any("class Gamma" in b for b in bodies)


def test_markdown_chunks_split_at_headings():
    md = "# A\nİlk bölüm metin.\n\n## B\nİkinci bölüm.\n\n# C\nÜçüncü bölüm.\n"
    chunks = _collect(chunk_markdown(md))
    assert len(chunks) == 3, f"3 heading bölümü beklendi, gelen {len(chunks)}"
    bodies = [c for _, c in chunks]
    assert bodies[0].startswith("# A")
    assert bodies[1].startswith("## B")
    assert bodies[2].startswith("# C")


def test_unknown_extension_falls_back_to_chars():
    text = "x" * 3000
    p = Path("/tmp/notes.txt")
    chunks = _collect(chunk_for_path(p, text, strategy="semantic"))
    assert len(chunks) == 2  # 3000 / 1500 = 2
    assert all(c == "x" * 1500 for _, c in chunks)


def test_invalid_python_falls_back_gracefully():
    bad = "def broken(:\n    pass\n"
    # should not throw any exception
    chunks = _collect(chunk_python(bad))
    assert chunks, "char-fallback boş döndü"
    # Char strategy explicit
    p = Path("/tmp/x.py")
    forced = _collect(chunk_for_path(p, bad, strategy="semantic"))
    assert forced, "chunk_for_path invalid python'da boş dönmemeli"


def test_chunk_chars_handles_empty():
    assert _collect(chunk_chars("")) == []


def test_python_no_definitions_falls_back_to_chars():
    src = "x = 1\ny = 2\n" * 200
    chunks = _collect(chunk_python(src))
    # no boundary → char fallback
    assert chunks
    assert all(len(c) <= 1500 for _, c in chunks)


def test_markdown_without_headings_falls_back_to_chars():
    text = "düz paragraf metin " * 100
    chunks = _collect(chunk_markdown(text))
    assert chunks
