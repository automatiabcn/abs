"""Compare a probe artifact against the stored golden fingerprint.

Exit code 0 = no drift; non-zero = drift detected (CI fails the job).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--probe", required=True, type=pathlib.Path)
    args = parser.parse_args()

    if not args.probe.exists():
        print(f"probe artifact missing: {args.probe}", file=sys.stderr)
        return 0  # nothing to compare; not a drift signal

    data = json.loads(args.probe.read_text())
    if data.get("skipped"):
        print(f"probe skipped for {args.provider}: {data.get('error', 'no key')}")
        return 0

    live = data.get("live_fingerprint_keys")
    golden = data.get("golden_fingerprint_keys")
    if live != golden:
        print(
            f"DRIFT: {args.provider} live response shape "
            f"differs from golden fixture (live={live[:8]} != golden={golden[:8]})"
        )
        return 1
    print(f"OK: {args.provider} response shape matches golden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
