#!/bin/bash
# DEPRECATED alias — delegates to anti-ek-swarm-review.sh (PATH + review + grok).
# Usage: ./scripts/swarm-review-pr.sh [--check|--dry-run] [base-ref]
# Cite: docs/anti-ek-cli-swarm.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/anti-ek-swarm-review.sh" "$@"
