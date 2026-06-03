#!/usr/bin/env bash
# ANT-EXEC-H2V SPR-05 — agent wrapper for AMS ref-lint (Phase E bounded closure).
#
# Thin entry for executors closing handoffs that cite UI/spec paths. Calls the
# canonical AMS ref-lint (tools/ams-v2/ref-lint.sh → verify_spec_refs.ts).
#
# USAGE
#   scripts/agent_ams_ref_lint.sh <sprint.html> [more.html …]
#   scripts/agent_ams_ref_lint.sh --json <sprint.html>
#
# See docs/agent-execution/AMS_BRIDGE.md for Phase E mapping and when to run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/tools/ams-v2/ref-lint.sh" "$@"