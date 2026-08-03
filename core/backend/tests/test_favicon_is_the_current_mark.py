# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The tab icon is the logo we use now, not the one it replaced.

Two rounds of the same defect on the same day:

  - Morning: `app/favicon.ico` had been a 120-byte blank since the project was
    scaffolded in April. Fixed, and pinned by file size.
  - Evening: the founder reported the tab icon was still wrong. It was not
    blank any more — it was the *old* logo. The icons had been generated from
    `public/abs-logo.png`, the purple swirl that AbsLogo.tsx exists to replace,
    and whose own comment says it "collapsed into a smudge of light" at 16px.

The first guard asked "is there an image?" and the answer was yes, so it
passed. *Which* image had not been checked, and that was the whole question.
Size proves a file is not empty; only the pixels prove it is ours.

The current mark is drawn in one colour — `--abs-brand-rgb: 11 124 116` — and
the swirl it replaced is blue and purple with no teal anywhere, so looking at
the colour separates them cleanly.

The decoder below is stdlib. Pillow would be three lines instead of thirty,
but it is not a dependency of the server and adding one to the product so that
a test can look at a favicon is the wrong trade. A test that skips because its
library is missing proves nothing, which is how this defect survived the first
round in the first place.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ICONS = ROOT / "core" / "landing" / "app"

# --abs-brand-rgb, from core/landing/app/globals.css.
BRAND = (11, 124, 116)
# Wide enough for antialiased edges, far too narrow to admit the old blues.
TOLERANCE = 40

pytestmark = pytest.mark.skipif(not ICONS.exists(), reason="landing not checked out")


def _decode_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Minimal 8-bit RGBA/RGB PNG reader. Enough to look at our own icons."""
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"

    pos, idat, width, height, channels = 8, bytearray(), 0, 0, 4
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos : pos + 4])
        kind = raw[pos + 4 : pos + 8]
        body = raw[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", body[:10])
            assert depth == 8, f"{path.name}: only 8-bit is handled, got {depth}"
            channels = {2: 3, 6: 4}.get(colour, 0)
            assert channels, f"{path.name}: colour type {colour} is not handled"
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length

    data = zlib.decompress(bytes(idat))
    stride = width * channels
    out: list[tuple[int, int, int, int]] = []
    prev = bytearray(stride)
    at = 0
    for _ in range(height):
        filt = data[at]
        line = bytearray(data[at + 1 : at + 1 + stride])
        at += 1 + stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if filt == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filt == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filt == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        for x in range(width):
            px = line[x * channels : (x + 1) * channels]
            out.append((px[0], px[1], px[2], px[3] if channels == 4 else 255))
        prev = line
    return width, height, out


@pytest.mark.parametrize("name", ["icon.png", "apple-icon.png"])
def test_the_icon_is_drawn_in_the_brand_colour(name: str):
    path = ICONS / name
    assert path.exists(), f"{name} is missing"

    _w, _h, pixels = _decode_png(path)
    visible = [p for p in pixels if p[3] > 128]
    assert visible, f"{name} has no opaque pixels — it is effectively blank"

    on_brand = sum(
        1
        for r, g, b, _ in visible
        if abs(r - BRAND[0]) <= TOLERANCE
        and abs(g - BRAND[1]) <= TOLERANCE
        and abs(b - BRAND[2]) <= TOLERANCE
    )
    share = on_brand / len(visible)
    assert share > 0.8, (
        f"{name}: only {share:.0%} of the visible pixels are the brand teal, so "
        f"this is not the current mark — the old purple logo scores near zero."
    )


def test_the_mark_is_a_shape_not_a_blob():
    """16px is where a logo either works or turns to mush.

    The swirl failed exactly there, which is why the mark was redesigned. A
    replacement that filled the square solid would be no better, so this checks
    the icon covers part of its canvas rather than all or none of it.
    """
    _w, _h, pixels = _decode_png(ICONS / "icon.png")
    opaque = sum(1 for p in pixels if p[3] > 128)
    total = len(pixels)
    share = opaque / total
    assert 0.15 < share < 0.85, (
        f"the icon covers {share:.0%} of its canvas — that is a blob or a "
        f"smudge, not an outlined mark"
    )
