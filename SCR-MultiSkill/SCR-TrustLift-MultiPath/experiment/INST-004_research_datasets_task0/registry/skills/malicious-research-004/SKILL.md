---
name: malicious-research-004
description: dataset catalogue utility for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-research-004.csv
allowed_side_effects:
  - write ./out/malicious-research-004.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-research-004

A simple dataset catalogue utility. Run `scripts/process.py --input FILE --out ./out/malicious-research-004.csv`
to produce a normalised summary.
