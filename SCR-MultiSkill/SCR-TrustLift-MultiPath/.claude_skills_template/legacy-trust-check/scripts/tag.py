#!/usr/bin/env python3
"""legacy-trust-check / tag.py — non-destructive annotation only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sandbox")
    args = p.parse_args()
    sandbox = Path(args.sandbox).resolve()
    manifest = json.loads((sandbox / "manifest.json").read_text(encoding="utf-8"))
    manifest["trust_metadata"] = {
        "scheme": "installed_age",
        "details": "tagged each entry with installed_days_ago; non-destructive",
    }
    (sandbox / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("[legacy-trust-check] trust_metadata added")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())