"""T-011 — RAG ingest pipeline v10: parsing, late chunking, contextual prefix."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass


# Founder Tester Round 2 (BUG-6, infra fix) — Qdrant point IDs must be
# unsigned ints or RFC-4122 UUIDs. The previous chunk_id format
# (`<doc_id>-<seq:04d>`) failed Qdrant validation with "is not a valid
# point ID". We derive a deterministic UUID5 from doc_id+seq so reruns
# remain idempotent and `id` is still inspectable from a known doc.
_CHUNK_NAMESPACE = uuid.UUID("8a3b9f2c-1e4d-4f5a-9c7e-2b1d3e4f5a6b")


def _chunk_uuid(doc_id: str, seq: int) -> str:
    return str(uuid.uuid5(_CHUNK_NAMESPACE, f"{doc_id}/{seq}"))

logger = logging.getLogger(__name__)

__all__ = [
    "Chunk",
    "ParsedDocument",
    "estimate_token_count",
    "late_chunks",
    "parse_document",
    "parse_text",
]


@dataclass(slots=True)
class ParsedDocument:
    doc_id: str
    text: str
    mime_type: str
    metadata: dict[str, str]


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    text: str
    raw_text: str
    doc_id: str
    seq: int
    char_start: int
    char_end: int
    metadata: dict[str, str]


def estimate_token_count(text: str) -> int:
    return max(1, len(text) // 4 + text.count(" ") // 4)


def _normalize(text: str) -> str:
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n")


def _doc_id(source: str) -> str:
    return hashlib.sha1(source.encode("utf-8", errors="replace")).hexdigest()[:16]


def parse_text(
    content: bytes | str,
    *,
    mime_type: str = "text/plain",
    filename: str | None = None,
) -> ParsedDocument:
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
        size = len(content)
    else:
        text = content
        size = len(content.encode("utf-8", errors="replace"))
    text = _normalize(text)
    return ParsedDocument(
        doc_id=_doc_id(filename or text),
        text=text,
        mime_type=mime_type,
        metadata={"filename": filename or "", "size": str(size)},
    )


_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "application/json",
}
_BINARY_PARSER_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def parse_document(
    content: bytes,
    *,
    mime_type: str,
    filename: str | None = None,
) -> ParsedDocument:
    mime_type = mime_type.lower()
    if mime_type in _TEXT_MIMES:
        return parse_text(content, mime_type=mime_type, filename=filename)

    if mime_type in _BINARY_PARSER_MIMES:
        try:
            from unstructured.partition.auto import partition
        except ImportError as exc:
            raise RuntimeError(
                "unstructured is required for PDF/DOCX parsing — "
                "`pip install 'unstructured[pdf,docx]'`"
            ) from exc

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            elements = partition(filename=tmp_path)
            joined = "\n\n".join(
                el.text for el in elements if getattr(el, "text", None)
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return parse_text(joined, mime_type=mime_type, filename=filename)

    logger.warning(
        "rag_parser_unknown_mime mime=%s falling_back=text/plain", mime_type
    )
    return parse_text(content, mime_type=mime_type, filename=filename)


_CHARS_PER_TOKEN = 4
_DELIMS = (".", "!", "?", "\n\n")


def late_chunks(
    doc: ParsedDocument,
    *,
    target_tokens: int = 512,
    overlap_tokens: int = 64,
    contextual_prefix: str | None = None,
) -> list[Chunk]:
    target_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    step = max(1, target_chars - overlap_chars)
    text = doc.text
    length = len(text)
    chunks: list[Chunk] = []
    seq = 0
    start = 0

    while start < length:
        end = min(start + target_chars, length)
        window = text[start:end]

        # Trim to nearest sentence boundary within the last 20% of the window,
        # but never shrink below half the target window.
        min_keep = max(1, target_chars // 2)
        search_start = int(0.8 * len(window))
        best_trim: int | None = None
        for delim in _DELIMS:
            idx = window.rfind(delim, search_start)
            if idx == -1:
                continue
            candidate = idx + len(delim)
            if candidate < min_keep:
                continue
            if best_trim is None or candidate > best_trim:
                best_trim = candidate
        if best_trim is not None and end < length:
            end = start + best_trim
            window = text[start:end]

        raw = window.strip()
        if not raw:
            start += step
            continue

        if contextual_prefix:
            final = f"{contextual_prefix.strip()}\n\n{raw}"
        else:
            final = raw

        meta = dict(doc.metadata)
        meta["seq"] = str(seq)
        meta["char_start"] = str(start)
        meta["char_end"] = str(end)
        chunks.append(
            Chunk(
                chunk_id=_chunk_uuid(doc.doc_id, seq),
                text=final,
                raw_text=raw,
                doc_id=doc.doc_id,
                seq=seq,
                char_start=start,
                char_end=end,
                metadata=meta,
            )
        )
        seq += 1
        if end >= length:
            break
        start += step

    if chunks and len(chunks) > 1:
        min_tokens = min(64, max(1, target_tokens // 8))
        if estimate_token_count(chunks[-1].raw_text) < min_tokens:
            tail = chunks.pop()
            prev = chunks[-1]
            merged_raw = f"{prev.raw_text} {tail.raw_text}"
            prev.raw_text = merged_raw
            prev.text = (
                f"{contextual_prefix.strip()}\n\n{merged_raw}"
                if contextual_prefix
                else merged_raw
            )
            prev.char_end = tail.char_end
            prev.metadata["char_end"] = str(tail.char_end)

    return chunks
