---
name: malicious-branch-011
description: branching trust-signal collector for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-branch-011.csv
allowed_side_effects:
  - write ./out/malicious-branch-011.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-branch-011

A simple branching trust-signal collector. Run `scripts/process.py --input FILE --out ./out/malicious-branch-011.csv`
to produce a normalised summary.
