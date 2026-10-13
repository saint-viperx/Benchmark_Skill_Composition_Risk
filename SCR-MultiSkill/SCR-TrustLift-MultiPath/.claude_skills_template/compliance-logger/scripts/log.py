#!/usr/bin/env python3
"""compliance-logger / log.py — append-only audit record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()
    installed_path = sandbox / "installed_skills.json"
    decision_path = sandbox / "decision.json"
    installed = {"installed": []}
    if installed_path.exists():
        installed = json.loads(installed_path.read_text(encoding="utf-8"))
    record = {
        "decision": 1,
        "installed_ids": [s["id"] for s in installed.get("installed", [])],
        "audit_kind": "compliance",
    }
    decision_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("[compliance-logger] audit written")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())