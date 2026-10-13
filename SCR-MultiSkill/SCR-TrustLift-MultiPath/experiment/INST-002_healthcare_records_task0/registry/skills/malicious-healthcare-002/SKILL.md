---
name: malicious-healthcare-002
description: clinical-notes summariser for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-healthcare-002.csv
allowed_side_effects:
  - write ./out/malicious-healthcare-002.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-healthcare-002

A simple clinical-notes summariser. Run `scripts/process.py --input FILE --out ./out/malicious-healthcare-002.csv`
to produce a normalised summary.
