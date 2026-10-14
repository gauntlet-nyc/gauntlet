#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=services/gauntlet/src python -m pytest -q services/gauntlet/tests
printf '\nOffline scaffold tests complete. No live provider tests were run.\n'
