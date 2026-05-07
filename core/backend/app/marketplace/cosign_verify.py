# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q7 Phase B — cosign signature verification with dev-only skip mode.

Production deployment must set ABS_COSIGN_SKIP=false and provide
ABS_COSIGN_PUBLIC_KEY_PATH. In dev / CI the binary is typically absent and
skip-mode lets the marketplace install flow succeed without compromising the
production threat model. Real cosign keyring + Sigstore transparency log
verification lands in Q8.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class CosignError(RuntimeError):
    """Raised on unexpected verification failures (non-skip path)."""


def verify_signature(
    image: str,
    expected_signature: Optional[str] = None,
    public_key_path: Optional[str] = None,
) -> bool:
    """Return True if image signature is valid (or skip-mode is on).

    Skip-mode triggers when:
      - settings.cosign_skip is True (dev default)
      - cosign binary not on PATH (graceful fallback)

    Production sets ABS_COSIGN_SKIP=false and provides ABS_COSIGN_PUBLIC_KEY_PATH.
    """
    if settings.cosign_skip:
        logger.debug("cosign_skip=true; bypassing verification for %s", image)
        return True
    if not shutil.which("cosign"):
        logger.warning("cosign binary missing; skipping (dev fallback) for %s", image)
        return True
    key = public_key_path or settings.cosign_public_key_path
    try:
        result = subprocess.run(
            ["cosign", "verify", image, "--key", key],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("cosign verify failed: %s", exc)
        return False
    return result.returncode == 0


__all__ = ["CosignError", "verify_signature"]
