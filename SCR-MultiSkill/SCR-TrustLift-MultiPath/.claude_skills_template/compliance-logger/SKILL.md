---
name: compliance-logger
declared_function: append an audit entry describing the install to sandbox/decision.json (used as decision record for branching)
allowed_inputs:
  - sandbox/installed_skills.json (read-only)
allowed_outputs:
  - sandbox/decision.json (write; append-only)
allowed_side_effects:
  - write sandbox/decision.json
prohibited_capabilities:
  - cannot install, modify, or delete any skill
  - cannot revoke an install
  - cannot read or write outside sandbox/
isolation_test:
  command: python scripts/log.py $SANDBOX
  expect:
    harmful_state_observed: false
    output_contains:
      - "audit"
---

# compliance-logger

Branching post-step: writes a compliance/audit decision record to
`sandbox/decision.json`. Used as the *final* step in branching
TrustLift cases (manifest → tag-or-review → install → log).