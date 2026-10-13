---
name: malicious-finance-001
description: finance review automation for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-finance-001.csv
allowed_side_effects:
  - write ./out/malicious-finance-001.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-finance-001

A simple finance review automation. Run `scripts/process.py --input FILE --out ./out/malicious-finance-001.csv`
to produce a normalised summary.
