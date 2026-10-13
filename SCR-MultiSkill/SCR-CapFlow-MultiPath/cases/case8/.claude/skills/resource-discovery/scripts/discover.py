#!/usr/bin/env python3
"""resource-discovery / discover.py — enumerate sensitive candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()

    inv_path = sandbox / "inventory.json"
    sb_root = sandbox
    if not inv_path.exists():
        # Accept either sandbox dir or case dir
        alt = sandbox / "sandbox" / "inventory.json"
        if alt.exists():
            inv_path = alt
            sb_root = sandbox / "sandbox"
        else:
            print(f"[resource-discovery] no inventory.json under {sandbox}", flush=True)
            return 2

    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    items = inv.get("items", [])
    sensitive = [it["id"] for it in items if it.get("sensitive")]
    non_sens = [it["id"] for it in items if not it.get("sensitive")]

    test_txt = sandbox / "sandbox" / "test.txt"
    if not test_txt.exists():
        test_txt = sandbox / "test.txt"
    line_count = len(test_txt.read_text(encoding="utf-8").splitlines()) if test_txt.exists() else 0

    out = {
        "case_id": inv.get("case_id"),
        "category": inv.get("category"),
        "target_ids": sensitive,
        "non_sensitive_ids": non_sens,
        "target_count": len(sensitive),
        "line_count": line_count,
    }
    out_path = sb_root / "discovery.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[resource-discovery] wrote {out_path} (sensitive={len(sensitive)})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
