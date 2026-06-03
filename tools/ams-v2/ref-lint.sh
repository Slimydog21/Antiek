#!/usr/bin/env bash
# AMS-v2 ref-lint — shell entry for anti-fiction path gate (SPR-01 M2).
#
# Delegates to tools/specs/verify_spec_refs.ts. Exists so sprint pages and
# agent-execution docs cite a stable tools/ams-v2/ path (see AMS_BRIDGE.md).
#
# USAGE
#   tools/ams-v2/ref-lint.sh <sprint.html> [more.html …]
#   tools/ams-v2/ref-lint.sh --json <sprint.html>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ $# -eq 0 ]]; then
  echo "usage: tools/ams-v2/ref-lint.sh [--json] <sprint.html> [more.html …]" >&2
  exit 2
fi

exec npx --yes tsx tools/specs/verify_spec_refs.ts "$@"