#!/usr/bin/env python3
"""selector-branch-size / select_largest.py — pick by item_size tag."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()

    candidates = [sandbox / "discovery.json", sandbox / "sandbox" / "discovery.json"]
    disc = None
    for c in candidates:
        if c.exists():
            disc = c
            break
    if disc is None:
        return 2

    d = json.loads(disc.read_text(encoding="utf-8"))
    inv_p = sandbox / "sandbox" / "inventory.json"
    if not inv_p.exists():
        inv_p = sandbox / "inventory.json"
    inv = json.loads(inv_p.read_text(encoding="utf-8"))
    items_by_id = {it["id"]: it for it in inv.get("items", [])}
    targets = d.get("target_ids") or []
    selected = max(targets, key=lambda tid: items_by_id.get(tid, {}).get("item_size", 0))

    out = {
        "case_id": d.get("case_id"),
        "selected_ids": [selected],
        "selection_rule": "branch-size",
    }
    out_path = sandbox / "sandbox" / "target_set.json"
    if not out_path.parent.exists():
        out_path = sandbox / "target_set.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[selector-branch-size] selected {selected}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
