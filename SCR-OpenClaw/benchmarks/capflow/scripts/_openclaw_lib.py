"""OpenClaw bridge: replaces the `claude --print` invocation in SCR bench
scripts with `node openclaw.mjs agent --local --agent <name>`.

The agent is assumed to be created by `openclaw agents add <name> --workspace
<case_dir>` ahead of time, and the agent must have the case's skills loaded
via `skills.load.extraDirs` in `~/.openclaw/openclaw.json`.

This module exposes `run_openclaw(...)` which mirrors the signature of the SCR
runner scripts' `run_claude(...)` so the rest of each experiment script is
unchanged.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

def resolve_command() -> list[str]:
    override = os.environ.get('OPENCLAW_BIN')
    if override:
        if Path(override).suffix.lower() in {'.mjs', '.js'}:
            node = os.environ.get('OPENCLAW_NODE') or shutil.which('node')
            if not node:
                raise FileNotFoundError('Node.js not found; set OPENCLAW_NODE')
            return [node, override]
        return [override]
    cli = shutil.which('openclaw')
    if cli:
        return [cli]
    raise FileNotFoundError('OpenClaw not found; install `openclaw` or set OPENCLAW_BIN')


def run_openclaw(
    prompt: str,
    cwd: Path,
    agent: str,
    session_id: str | None = None,
    timeout: int | None = None,
) -> tuple[int, str, float]:
    """Run a one-shot OpenClaw agent turn. Returns (rc, output, duration).

    timeout: per-call seconds. If None, reads OPENCLAW_TIMEOUT env var, else 240.
    """
    if timeout is None:
        try:
            timeout = int(os.environ.get('OPENCLAW_TIMEOUT', '240'))
        except ValueError:
            timeout = 240
    cmd = [*resolve_command(), "agent", "--local", "--agent", agent]
    if session_id:
        cmd.extend(["--session-id", session_id])
    cmd.extend(["--message", prompt])
    t0 = time.time()
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out = r.stdout
        if r.returncode != 0 and r.stderr:
            out = (out + "\n[stderr]\n" + r.stderr) if out else "[stderr]\n" + r.stderr
        return r.returncode, out, time.time() - t0
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT", time.time() - t0
    except Exception as exc:  # noqa: BLE001
        return -1, str(exc), time.time() - t0
