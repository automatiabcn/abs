#!/usr/bin/env bash
# Build abs-vmhost — the Tier-2 microVM helper.
#
# The signing step is not optional and not cosmetic: Virtualization.framework
# refuses EVERY configuration from a process without the
# com.apple.security.virtualization entitlement, with an error that reads like
# a configuration mistake. Measured on this machine (08-01): unsigned, the
# framework said "the process doesn't have the entitlement"; ad-hoc signed
# with the entitlement, it accepted the same configuration.
#
#   tools/vmhost/build.sh              # build + ad-hoc sign, into this dir
#   tools/vmhost/build.sh /usr/local/bin   # and install it on PATH
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/abs-vmhost"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "✗ abs-vmhost is the macOS helper; Linux Tier-2 uses KVM instead." >&2
    exit 1
fi

echo "▶ compiling"
swiftc -O -framework Virtualization -o "$OUT" "$HERE/probe.swift"

echo "▶ signing with the virtualization entitlement"
codesign --force --entitlements "$HERE/vmhost.entitlements" --sign - "$OUT"

echo "▶ asking the framework what this machine can do"
"$OUT" --probe || true   # a "not yet" answer is information, not a build failure

if [[ $# -ge 1 ]]; then
    install -m 0755 "$OUT" "$1/abs-vmhost"
    echo "installed -> $1/abs-vmhost"
fi
