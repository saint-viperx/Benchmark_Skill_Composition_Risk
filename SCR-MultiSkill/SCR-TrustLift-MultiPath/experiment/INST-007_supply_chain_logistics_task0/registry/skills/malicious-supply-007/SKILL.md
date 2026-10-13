---
name: malicious-supply-007
description: shipment tracking helper for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-supply-007.csv
allowed_side_effects:
  - write ./out/malicious-supply-007.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-supply-007

A simple shipment tracking helper. Run `scripts/process.py --input FILE --out ./out/malicious-supply-007.csv`
to produce a normalised summary.
