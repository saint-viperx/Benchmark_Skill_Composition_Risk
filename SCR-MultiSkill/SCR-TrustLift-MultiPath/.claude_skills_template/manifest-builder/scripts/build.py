#!/usr/bin/env python3
"""manifest-builder / build.py — pure enumeration, no evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()
    inv = json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))
    installed = {s["id"] for s in inv.get("installed", [])}
    registry = inv.get("registry", [])
    manifest = {
        "case_id": inv.get("case_id"),
        "installed": sorted(installed),
        "available": [r["id"] for r in registry if r["id"] not in installed],
        "registry_size": len(registry),
    }
    (sandbox / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[manifest-builder] manifest written: {manifest['registry_size']} entries")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())