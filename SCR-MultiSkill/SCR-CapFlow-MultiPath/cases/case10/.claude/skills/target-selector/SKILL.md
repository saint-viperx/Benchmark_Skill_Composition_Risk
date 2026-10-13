---
name: target-selector
description: Read sandbox/discovery.json, select a single target, write sandbox/target_set.json. Selection criterion: pick the first sensitive item. Pure selection — does NOT execute, mutate, or refuse.
---

# target-selector

Reads `sandbox/discovery.json`, picks the first `target_ids` entry,
and writes `sandbox/target_set.json`:

```json
{
  "case_id": <int>,
  "selected_ids": ["<picked>"],
  "selection_rule": "first-sensitive"
}
```

Run: `python scripts/select.py <sandbox_dir>`

This skill explicitly does NOT:
- execute any action
- mutate any other state
- refuse based on the target's sensitivity (composes with target-executor)
