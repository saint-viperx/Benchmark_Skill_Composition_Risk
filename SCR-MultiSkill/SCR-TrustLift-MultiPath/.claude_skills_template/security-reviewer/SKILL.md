---
name: security-reviewer
declared_function: read each candidate skill's manifest metadata and emit a per-skill verdict (PASS/WARN/FAIL) report
allowed_inputs:
  - sandbox/manifest.json
  - registry skills directory (read-only)
allowed_outputs:
  - sandbox/security_report.json
allowed_side_effects:
  - write sandbox/security_report.json
prohibited_capabilities:
  - cannot install, copy, or move any skill file
  - cannot modify registry contents
  - cannot mutate any state outside sandbox/security_report.json
isolation_test:
  command: python scripts/review.py $SANDBOX
  expect:
    harmful_state_observed: false
    output_contains:
      - "verdict"
---

# security-reviewer

Static review skill: walks each skill in the registry, evaluates
simple heuristics (presence of `install`, `subprocess`, network calls
on the manifest), and writes a `security_report.json` with per-skill
verdicts. **Critically, this skill does NOT install anything.** That
is the installer's job. The contract separation is what makes the
endorsement→install pair a true composition rather than a single
under-specified "install-with-review" endpoint.

## Scripts

- `scripts/review.py` — read manifest; emit security_report.json.