#!/usr/bin/env python3
# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Drive the editor agent from a terminal, with the editor's tools done in
Python over a folder — the same loop the editor runs, without the editor.

Why this exists: the 2026-09-01 transcript (RobotMarket) is a list of
developer messages the chat answered badly. This replays them against a
live backend and prints every tool call, so "the agent reads the file
instead of asking for it" is something we can watch, not assert.

    set -a; . .e2e-state/restart.env; set +a
    .venv/bin/python scripts/agent_replay.py --root /path/to/project \\
        --mode agent --apply "Login nerede tanımlı?" "evet yaptım kontrol et"

--apply writes approved edits and created files (use a scratch copy).
Without it, edits are shown and reported to the model as not approved.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import httpx

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".mypy_cache", ".pytest_cache"}
READ_ONLY = re.compile(r"^\s*(ls|cat|head|tail|wc|git (status|diff|log|show|branch)|grep|rg|find|pwd|python3? -c ['\"]print)\b")


def mint_token() -> str:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.api.mcp_tokens import _sign

    return _sign(
        {"tenant": "default", "scope": "all", "label": "replay", "exp": int(time.time()) + 3600, "actor": "replay@abs.local"}
    )


class Tools:
    def __init__(self, root: str, apply: bool, approve_all: bool, server: str, token: str):
        self.root = os.path.realpath(root)
        self.apply = apply
        self.approve_all = approve_all
        self.server = server.rstrip("/")
        self.token = token
        self.plan: List[Dict[str, Any]] = []
        self.applied: List[str] = []

    def _abs(self, rel: str) -> Optional[str]:
        rel = (rel or "").replace("\\", "/")
        while rel.startswith("./"):
            rel = rel[2:]
        full = os.path.realpath(os.path.join(self.root, rel))
        if full != self.root and not full.startswith(self.root + os.sep):
            return None
        return full

    def read_file(self, path: str = "", start_line: int = 0, end_line: int = 0, **_: Any) -> str:
        full = self._abs(path)
        if not full or not os.path.isfile(full):
            return f"read_file failed: {path} is not a file in the project."
        try:
            lines = open(full, encoding="utf-8", errors="replace").read().splitlines()
        except OSError as exc:
            return f"read_file failed: {exc}"
        n = len(lines)
        s = max(1, int(start_line or 1))
        e = min(n, int(end_line or n))
        if not start_line and not end_line and n > 400:
            e = 400
        body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(s, e + 1))
        note = f"\n… ({n - e} more lines; call again with start_line={e + 1})" if e < n else ""
        return f"{path} (lines {s}-{e} of {n}):\n{body}{note}"

    def list_dir(self, path: str = "", **_: Any) -> str:
        full = self._abs(path or "")
        if not full or not os.path.isdir(full):
            return f"list_dir failed: {path or '.'} is not a folder in the project."
        out = []
        for name in sorted(os.listdir(full)):
            if name in SKIP_DIRS or name.startswith(".") and name != ".abs":
                continue
            p = os.path.join(full, name)
            out.append(name + "/" if os.path.isdir(p) else name)
        return f"{path or '.'}: " + ", ".join(out[:200])

    def grep(self, pattern: str = "", glob: str = "", max_results: int = 40, **_: Any) -> str:
        try:
            rx = re.compile(pattern, re.I)
        except re.error as exc:
            return f"grep failed: bad pattern ({exc})"
        hits: List[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), self.root)
                if glob and not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(fn, glob):
                    continue
                try:
                    with open(os.path.join(dirpath, fn), encoding="utf-8", errors="strict") as fh:
                        for i, line in enumerate(fh, 1):
                            if rx.search(line):
                                hits.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                                if len(hits) >= int(max_results or 40):
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                if len(hits) >= int(max_results or 40):
                    break
        return "\n".join(hits) if hits else f"grep: no matches for /{pattern}/ in the project."

    def get_diagnostics(self, path: str = "", **_: Any) -> str:
        # The editor has language servers; here, a syntax check of Python files.
        targets = []
        if path:
            full = self._abs(path)
            targets = [full] if full and full.endswith(".py") else []
        else:
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                targets += [os.path.join(dirpath, f) for f in filenames if f.endswith(".py")]
        problems = []
        for t in targets[:300]:
            try:
                compile(open(t, encoding="utf-8").read(), t, "exec")
            except SyntaxError as exc:
                problems.append(f"{os.path.relpath(t, self.root)}:{exc.lineno}: error: {exc.msg}")
            except (OSError, UnicodeDecodeError):
                pass
        return "\n".join(problems) if problems else "No problems reported."

    def git_diff(self, path: str = "", **_: Any) -> str:
        if not os.path.isdir(os.path.join(self.root, ".git")):
            return "git_diff: this project is not a git repository, so there is no diff to show. Read the files directly."
        cmd = ["git", "diff", "--no-color"] + ([path] if path else [])
        out = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True).stdout
        return out[:12000] if out.strip() else "git_diff: the working tree is clean (no uncommitted changes)."

    def run_command(self, command: str = "", timeout_s: int = 60, **_: Any) -> str:
        if not (self.approve_all or READ_ONLY.match(command or "")):
            return f"run_command: '{command}' needs the developer's approval and was not approved in this session."
        try:
            p = subprocess.run(command, cwd=self.root, shell=True, capture_output=True, text=True, timeout=int(timeout_s or 60))
        except subprocess.TimeoutExpired:
            return f"run_command: timed out after {timeout_s}s"
        out = (p.stdout + p.stderr)[-6000:]
        return f"exit code {p.returncode}\n{out}"

    def run_tests(self, command: str = "", path: str = "", **_: Any) -> str:
        if not command:
            py = os.path.join(self.root, ".venv", "bin", "python")
            py = py if os.path.exists(py) else sys.executable
            command = f"{py} -m pytest -q -x --no-header {path or ''}".strip()
        return self.run_command(command, timeout_s=180) if self.approve_all or self.apply else (
            f"run_tests: '{command}' needs the developer's approval and was not approved in this session."
        )

    def update_plan(self, todos: Any = None, **_: Any) -> str:
        self.plan = [t for t in (todos or []) if isinstance(t, dict)]
        return f"Plan updated ({len(self.plan)} items):\n" + "\n".join(
            f"[{t.get('status')}] {t.get('id')}: {t.get('text')}" for t in self.plan
        )

    def ask_user(self, question: str = "", options: Any = None, **_: Any) -> str:
        return "__ASK_USER__" + question

    def create_file(self, path: str = "", content: str = "", **_: Any) -> str:
        full = self._abs(path)
        if not full:
            return f"create_file refused: {path} is outside the project."
        if os.path.exists(full):
            return f"create_file failed: {path} exists. Use propose_edit."
        if not self.apply:
            return f"create_file: {path} ({len(content.splitlines())} lines) was shown to the developer and NOT approved in this session."
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w", encoding="utf-8").write(content)
        self.applied.append(path)
        return f"APPLIED: created {path} ({len(content.splitlines())} lines)."

    def server_tool(self, name: str, args: Dict[str, Any]) -> str:
        r = httpx.post(
            f"{self.server}/v1/editor/agent/tool",
            json={"name": name, "args": args, "workspace_root": self.root},
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=120,
        )
        data = r.json()
        if name == "propose_edit" and data.get("ok"):
            print(f"      diff (+{data.get('added')}/-{data.get('removed')}, judge {data.get('judge_score')}):")
            for line in data["unified_diff"].splitlines()[:40]:
                print("      " + line)
            if self.apply:
                # The editor applies with its own diff applier; here the
                # server's patch engine does the same job, and its verdict is
                # the truth rather than `patch(1)`'s exit code.
                from app.patches import engine as patch_engine

                target = os.path.join(self.root, data["path"])
                res = patch_engine.apply(target, data["unified_diff"], backup=False, workspace_root=self.root)
                if getattr(res, "success", False):
                    self.applied.append(data["path"])
                    return f"APPLIED: {data['path']} (+{data.get('added')}/-{data.get('removed')}). The file now has the change."
                return f"The edit to {data['path']} could not be applied: {getattr(res, 'reason', '') or getattr(res, 'stage', '')}"
            return f"{data['model_note']} The developer did NOT approve it in this session."
        return str(data.get("model_note") or json.dumps(data)[:2000])

    def run(self, name: str, args: Dict[str, Any], where: str) -> str:
        if where == "server":
            return self.server_tool(name, args)
        fn = getattr(self, name, None)
        if fn is None:
            return f"System: there is no tool called '{name}'."
        return fn(**args)


def sse(resp: httpx.Response):
    buf = ""
    for chunk in resp.iter_text():
        buf += chunk
        while "\n\n" in buf:
            frame, buf = buf.split("\n\n", 1)
            for line in frame.splitlines():
                if line.startswith("data:"):
                    try:
                        yield json.loads(line[5:].strip())
                    except ValueError:
                        pass


def one_turn(tools: Tools, message: str, mode: str, history: str, max_steps: int, verbose: bool) -> str:
    steps: List[Dict[str, Any]] = []
    for _ in range(max_steps + 1):
        body = {
            "message": message,
            "mode": mode,
            "history": history,
            "workspace_root": tools.root,
            "plan": tools.plan,
            "steps": steps,
        }
        with httpx.stream(
            "POST",
            f"{tools.server}/v1/editor/agent/step",
            json=body,
            headers={"Authorization": f"Bearer {tools.token}"},
            timeout=180,
        ) as r:
            action = None
            final = None
            shown = ""
            for ev in sse(r):
                t = ev.get("type")
                if t == "meta":
                    print(f"  [step {ev['step']}] lang={ev['lang']} intent={ev['intent']} chain={ev['chain'][:2]} pre-read={ev['used_files']}")
                elif t == "provider":
                    print(f"      provider: {ev['name']}")
                elif t == "waiting":
                    print(f"      waiting {ev['seconds']}s (attempt {ev['attempt']}): {ev['reason'][:80]}")
                elif t == "leg_failed":
                    print(f"      leg failed: {ev['name']} — {ev['detail']}")
                elif t == "delta":
                    shown += ev["text"]
                elif t == "replace":
                    shown = ev["text"]
                elif t == "action":
                    action = ev
                elif t == "final":
                    final = ev
                elif t == "error":
                    print(f"      ERROR: {ev}")
                    return ""
        if action:
            args = json.dumps(action["args"], ensure_ascii=False)
            print(f"      → {action['name']} {args[:160]}")
            same = [s for s in steps if s["name"] == action["name"] and s["args"] == action["args"]]
            if action.get("error"):
                result = action["error"]
            elif same:
                result = "System: you already made this exact call; its result is above. Do not repeat it."
            else:
                result = tools.run(action["name"], action["args"], action["where"])
            if result.startswith("__ASK_USER__"):
                q = result[len("__ASK_USER__"):]
                print(f"  ABS asks: {q}")
                return f"(asked) {q}"
            if verbose:
                print("      " + result[:600].replace("\n", "\n      "))
            else:
                print(f"      ← {result.splitlines()[0][:140] if result else '(empty)'} [{len(result)} chars]")
            steps.append({"name": action["name"], "args": action["args"], "result": result})
            continue
        if final:
            flags = []
            if final.get("unverified"):
                flags.append(f"unverified={final['unverified']}")
            if final.get("lang_drift"):
                flags.append(f"drift={final['lang_drift']} regenerated={final['regenerated']}")
            if final.get("continued"):
                flags.append(f"continued={final['continued']}")
            print(f"  ABS ({final['provider']}, {final['elapsed_ms']}ms, {len(steps)} tools{', ' + ' '.join(flags) if flags else ''}):")
            print("    " + final["text"].strip().replace("\n", "\n    "))
            if not final["text"].strip():
                print("    (empty answer) final frame:", {k: v for k, v in final.items() if k != "text"})
            return final["text"]
    print("  (step budget exhausted)")
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("messages", nargs="+")
    ap.add_argument("--root", required=True)
    ap.add_argument("--mode", default="agent")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approve-all", action="store_true")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    tools = Tools(a.root, a.apply, a.approve_all, a.server, mint_token())
    history = ""
    for msg in a.messages:
        print(f"\nDeveloper: {msg}")
        answer = one_turn(tools, msg, a.mode, history, a.max_steps, a.verbose)
        history += f"Developer: {msg}\nABS: {answer[:1200]}\n"
    if tools.applied:
        print(f"\napplied: {tools.applied}")


if __name__ == "__main__":
    main()
