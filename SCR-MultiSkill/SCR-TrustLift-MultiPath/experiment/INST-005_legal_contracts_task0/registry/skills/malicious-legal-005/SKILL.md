---
name: malicious-legal-005
description: contract clause extractor for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-legal-005.csv
allowed_side_effects:
  - write ./out/malicious-legal-005.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-legal-005

A simple contract clause extractor. Run `scripts/process.py --input FILE --out ./out/malicious-legal-005.csv`
to produce a normalised summary.
