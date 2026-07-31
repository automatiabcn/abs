# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tier-1 containment on Windows: a WRITE_RESTRICTED token.

The seatbelt story, translated. A write-restricted token can only write
where the ``RESTRICTED`` well-known SID (S-1-5-12) is explicitly granted
write access; we grant it on the workspace and nowhere else, so the child
can read the user's world but change only the folder it was given.
``DISABLE_MAX_PRIVILEGE`` strips every privilege the user carries.

Two honesty rules shape this module:

* **Nothing is claimed before it is proven on THIS machine.** The mechanism
  reports available only after a self-test spawns a probe under the token
  and demonstrates all three: it runs, it CAN write inside the granted
  folder, and it CANNOT write outside it. Any error, any surprise —
  unavailable, and the caller keeps today's honest refusal.
* **What the tier does not do is said out loud.** A token does not block
  the network; :data:`NETWORK_NOTE` exists so callers never print
  "network off" over a mechanism that cannot promise it.

Written on macOS against the documented Win32 contracts; the self-test is
what stands between this file and a false "sandboxed" label on a machine
nobody has tried it on.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

MECHANISM = "restricted-token"
NETWORK_NOTE = "network is NOT blocked by this tier"

# Cached self-test verdict: None = never ran, True/False = proven.
_SELF_TEST: bool | None = None


def _grant_restricted_write(path: str) -> None:
    """Grant the RESTRICTED SID modify rights on ``path`` (icacls).

    ``*S-1-5-12`` is the well-known RESTRICTED SID: a WRITE_RESTRICTED
    token's writes are checked against it, so this grant is what turns
    "can write nowhere" into "can write exactly here". (OI)(CI) inherits
    to children; the grant lives on a folder we own, is idempotent, and a
    failed grant surfaces as a failed self-test, never as a silent pass.
    """
    subprocess.run(
        ["icacls", path, "/grant", "*S-1-5-12:(OI)(CI)M"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


def _spawn_restricted(argv: list[str], cwd: str, timeout: float):
    """Run ``argv`` under a WRITE_RESTRICTED, privilege-stripped token."""
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    TOKEN_ALL_ACCESS = 0xF01FF
    WRITE_RESTRICTED = 0x08
    DISABLE_MAX_PRIVILEGE = 0x01

    process_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), TOKEN_ALL_ACCESS, ctypes.byref(process_token)
    ):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
    restricted = wintypes.HANDLE()
    try:
        if not advapi32.CreateRestrictedToken(
            process_token,
            WRITE_RESTRICTED | DISABLE_MAX_PRIVILEGE,
            0, None,   # SidsToDisable
            0, None,   # PrivilegesToDelete (redundant under DISABLE_MAX_PRIVILEGE)
            0, None,   # RestrictedSids — empty list + WRITE_RESTRICTED means
                       # writes are checked against the RESTRICTED SID alone.
            ctypes.byref(restricted),
        ):
            raise OSError(ctypes.get_last_error(), "CreateRestrictedToken failed")

        # subprocess cannot take a token; CreateProcessAsUser can.
        class STARTUPINFO(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
            ]

        CREATE_NO_WINDOW = 0x08000000
        si = STARTUPINFO(); si.cb = ctypes.sizeof(si)
        pi = PROCESS_INFORMATION()
        cmdline = subprocess.list2cmdline(argv)
        if not advapi32.CreateProcessAsUserW(
            restricted, None, cmdline, None, None, False,
            CREATE_NO_WINDOW, None, cwd, ctypes.byref(si), ctypes.byref(pi),
        ):
            raise OSError(ctypes.get_last_error(), "CreateProcessAsUserW failed")
        try:
            WAIT_TIMEOUT = 0x102
            if kernel32.WaitForSingleObject(pi.hProcess, int(timeout * 1000)) == WAIT_TIMEOUT:
                kernel32.TerminateProcess(pi.hProcess, 1)
                raise subprocess.TimeoutExpired(cmdline, timeout)
            code = wintypes.DWORD()
            kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
            return int(code.value)
        finally:
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)
    finally:
        kernel32.CloseHandle(process_token)
        if restricted:
            kernel32.CloseHandle(restricted)


def self_test() -> bool:
    """Prove the containment on this machine, once. Any surprise = False."""
    global _SELF_TEST
    if _SELF_TEST is not None:
        return _SELF_TEST
    if sys.platform != "win32":
        _SELF_TEST = False
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="abs-sbx-probe-") as ws:
            _grant_restricted_write(ws)
            inside = os.path.join(ws, "inside.txt")
            outside = os.path.join(tempfile.gettempdir(), "abs-sbx-outside-probe.txt")
            try:
                os.unlink(outside)
            except OSError:
                pass
            # 1) it runs; 2) it can write where granted
            ok = _spawn_restricted(
                ["cmd", "/c", f"echo probe> {inside}"], ws, timeout=15
            )
            if ok != 0 or not os.path.exists(inside):
                raise RuntimeError("probe could not write inside the granted folder")
            # 3) it cannot write anywhere else
            _spawn_restricted(
                ["cmd", "/c", f"echo probe> {outside}"], ws, timeout=15
            )
            if os.path.exists(outside):
                os.unlink(outside)
                raise RuntimeError("probe wrote OUTSIDE the workspace — not contained")
        _SELF_TEST = True
    except Exception as exc:  # noqa: BLE001 — any surprise means "not proven"
        logger.warning("windows restricted-token self-test failed: %s", exc)
        _SELF_TEST = False
    return _SELF_TEST


def run(
    command: list[str],
    *,
    workspace_root: str,
    timeout: float,
) -> tuple[int, str, str]:
    """Run ``command`` write-confined to ``workspace_root``.

    Output is captured via files inside the workspace — the probe token has
    nowhere else to write, which is the point.
    """
    _grant_restricted_write(workspace_root)
    out_path = os.path.join(workspace_root, ".abs-sbx-out.txt")
    err_path = os.path.join(workspace_root, ".abs-sbx-err.txt")
    cmdline = subprocess.list2cmdline(command)
    wrapped = ["cmd", "/c", f"{cmdline} > {out_path} 2> {err_path}"]
    try:
        code = _spawn_restricted(wrapped, workspace_root, timeout)
        def _read(p: str) -> str:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            except OSError:
                return ""
        return code, _read(out_path), _read(err_path)
    finally:
        for p in (out_path, err_path):
            try:
                os.unlink(p)
            except OSError:
                pass
