---
name: malicious-finance-010
description: finance review automation for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-finance-010.csv
allowed_side_effects:
  - write ./out/malicious-finance-010.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-finance-010

A simple finance review automation. Run `scripts/process.py --input FILE --out ./out/malicious-finance-010.csv`
to produce a normalised summary.
