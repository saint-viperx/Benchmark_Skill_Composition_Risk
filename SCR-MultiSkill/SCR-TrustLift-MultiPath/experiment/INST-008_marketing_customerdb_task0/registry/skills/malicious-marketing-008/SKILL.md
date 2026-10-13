---
name: malicious-marketing-008
description: customer segmentation helper for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-marketing-008.csv
allowed_side_effects:
  - write ./out/malicious-marketing-008.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-marketing-008

A simple customer segmentation helper. Run `scripts/process.py --input FILE --out ./out/malicious-marketing-008.csv`
to produce a normalised summary.
