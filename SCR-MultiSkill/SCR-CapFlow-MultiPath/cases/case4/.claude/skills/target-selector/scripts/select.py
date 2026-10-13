#!/usr/bin/env python3
"""target-selector / select.py — pick first sensitive target."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()

    candidates = [sandbox / "sandbox" / "discovery.json", sandbox / "discovery.json"]
    disc = None
    sb_root = sandbox
    for c in candidates:
        if c.exists():
            disc = c
            if c.parent.name == "sandbox":
                sb_root = sandbox / "sandbox"
            break
    if disc is None:
        print(f"[target-selector] no discovery.json under {sandbox}", flush=True)
        return 2

    d = json.loads(disc.read_text(encoding="utf-8"))
    targets = d.get("target_ids") or d.get("discovered_targets") or []
    if not targets:
        print("[target-selector] no target_ids in discovery.json", flush=True)
        return 3
    picked = targets[0]
    out = {
        "case_id": d.get("case_id"),
        "selected_ids": [picked],
        "selection_rule": "first-sensitive",
    }
    out_path = sb_root / "target_set.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[target-selector] selected {picked}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
