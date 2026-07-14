# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""balanced-brace JSON extraction."""

from __future__ import annotations

import json
import re
from typing import Any, Optional


_FENCE_RX = re.compile(
    r"```(?:json|JSON)?\s*([\[{].*?[\]}])\s*```",
    re.DOTALL,
)


def _walk_balanced(text: str, opener: str, closer: str) -> Optional[str]:
    start = text.find(opener)
    if start == -1:
        return None
    depth = 0
    in_str = False
    str_quote = ""
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == str_quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(raw: str, default: Any = None) -> Any:
    if not raw:
        return default
    text = raw.strip()
    fence = _FENCE_RX.search(text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    obj_idx = text.find("{")
    arr_idx = text.find("[")
    if obj_idx == -1 and arr_idx == -1:
        return default
    if obj_idx == -1:
        order = [("[", "]")]
    elif arr_idx == -1:
        order = [("{", "}")]
    elif obj_idx < arr_idx:
        order = [("{", "}"), ("[", "]")]
    else:
        order = [("[", "]"), ("{", "}")]
    for opener, closer in order:
        chunk = _walk_balanced(text, opener, closer)
        if chunk is None:
            continue
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return default


__all__ = ["extract_json"]
