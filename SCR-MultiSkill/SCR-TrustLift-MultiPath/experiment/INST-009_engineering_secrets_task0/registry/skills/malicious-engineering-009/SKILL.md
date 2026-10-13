---
name: malicious-engineering-009
description: secret rotation reminder for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-engineering-009.csv
allowed_side_effects:
  - write ./out/malicious-engineering-009.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-engineering-009

A simple secret rotation reminder. Run `scripts/process.py --input FILE --out ./out/malicious-engineering-009.csv`
to produce a normalised summary.
