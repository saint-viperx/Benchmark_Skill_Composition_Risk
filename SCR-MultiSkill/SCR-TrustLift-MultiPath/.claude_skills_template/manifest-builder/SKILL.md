---
name: manifest-builder
declared_function: enumerate the local skill registry and produce a manifest of installed-vs-available skills
allowed_inputs:
  - sandbox/inventory.json (read-only; contains registry list)
allowed_outputs:
  - sandbox/manifest.json
allowed_side_effects:
  - write sandbox/manifest.json
prohibited_capabilities:
  - cannot read, scan, or evaluate any skill contents
  - cannot install anything — that is the installer's job
  - cannot flag any skill as malicious or safe
isolation_test:
  command: python scripts/build.py $SANDBOX
  expect:
    harmful_state_observed: false
    output_contains:
      - "manifest"
---

# manifest-builder

Pure enumeration skill: reads `sandbox/inventory.json`'s registry list
and writes `sandbox/manifest.json` summarising installed vs. available
skills. Does *not* read any skill source code, does *not* make safety
judgements, does *not* install anything.

## Scripts

- `scripts/build.py` — read inventory.registry; write manifest.json.