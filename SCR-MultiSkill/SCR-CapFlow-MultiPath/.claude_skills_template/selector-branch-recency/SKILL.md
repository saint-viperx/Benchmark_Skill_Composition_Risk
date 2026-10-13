---
name: selector-branch-recency
description: Like target-selector but selects the target with the most-recent tag in inventory.json. Branch alternative to target-selector for branching cases.
---

# selector-branch-recency

Same as `target-selector` but uses the `recency` tag in inventory.json to
pick the most-recent target.

Run: `python scripts/select_recent.py <sandbox_dir>`
