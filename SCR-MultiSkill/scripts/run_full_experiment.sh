#!/usr/bin/env bash
# Bash wrapper that runs the orchestrator from the SCR-MultiSkill root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

exec python "${SCRIPT_DIR}/run_full_experiment.py" "$@"
