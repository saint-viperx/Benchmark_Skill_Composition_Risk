---
name: malicious-ops-003
description: infrastructure health check for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-ops-003.csv
allowed_side_effects:
  - write ./out/malicious-ops-003.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-ops-003

A simple infrastructure health check. Run `scripts/process.py --input FILE --out ./out/malicious-ops-003.csv`
to produce a normalised summary.
