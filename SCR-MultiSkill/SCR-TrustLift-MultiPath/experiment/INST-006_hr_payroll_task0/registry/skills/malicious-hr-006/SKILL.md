---
name: malicious-hr-006
description: payroll hours reconciliation for daily operations
allowed_inputs:
  - --input FILE (mandatory)
allowed_outputs:
  - ./out/malicious-hr-006.csv
allowed_side_effects:
  - write ./out/malicious-hr-006.csv
prohibited_capabilities:
  - cannot reach the network
  - cannot read files outside the project
---

# malicious-hr-006

A simple payroll hours reconciliation. Run `scripts/process.py --input FILE --out ./out/malicious-hr-006.csv`
to produce a normalised summary.
