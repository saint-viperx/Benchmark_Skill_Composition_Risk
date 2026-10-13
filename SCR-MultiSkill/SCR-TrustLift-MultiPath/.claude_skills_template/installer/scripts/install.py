#!/usr/bin/env python3
"""installer / install.py — copies one skill from registry to project .claude/skills/."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    p.add_argument("--skill", required=True)
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()
    inv = json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))
    registry = {r["id"]: r for r in inv.get("registry", [])}
    if args.skill not in registry:
        print(f"[installer] refused: {args.skill} not in registry", file=sys.stderr)
        return 2
    src = Path(registry[args.skill]["path"])
    if not src.is_absolute():
        src = sandbox / src
    if not src.exists():
        print(f"[installer] refused: registry path missing {src}", file=sys.stderr)
        return 3
    dst = sandbox / ".claude" / "skills" / args.skill
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    installed_path = sandbox / "installed_skills.json"
    installed = {"installed": []}
    if installed_path.exists():
        installed = json.loads(installed_path.read_text(encoding="utf-8"))
    installed["installed"] = installed.get("installed", []) + [
        {"id": args.skill, "status": "installed"}
    ]
    installed_path.write_text(json.dumps(installed, indent=2), encoding="utf-8")
    print(f"[installer] installed {args.skill}")
    return 0


if __name__ == "__main__":
    sys.exit(main())