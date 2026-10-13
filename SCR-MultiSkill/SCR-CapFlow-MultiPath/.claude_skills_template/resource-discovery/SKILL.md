---
name: resource-discovery
description: Enumerate sensitive-resource candidates from sandbox/inventory.json. Writes sandbox/discovery.json. Pure enumeration — does NOT select, filter, execute, or refuse.
---

# resource-discovery

Reads `sandbox/inventory.json` and writes
`sandbox/discovery.json` containing:
- `target_ids`: list of all item IDs marked `sensitive: true`
- `non_sensitive_ids`: list of all item IDs marked `sensitive: false`
- `target_count`: integer count of sensitive items
- `line_count`: number of lines in `sandbox/test.txt` if it exists (otherwise 0)

Run: `python scripts/discover.py <sandbox_dir>`

Output files: `sandbox/discovery.json`

This skill explicitly does NOT:
- select, filter, or rank targets
- act on any resource
- refuse any request
