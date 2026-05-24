#!/usr/bin/env bash
# scripts/install_hooks.sh — point this clone's git at .githooks/.
#
# Antiek ships its hooks in-repo at .githooks/ so they version with
# the code. Git, however, does not enable an in-repo hook directory
# by default — each clone must opt in via core.hooksPath.
#
# This script is the opt-in. Run it once after cloning:
#
#     ./scripts/install_hooks.sh
#
# Idempotent: subsequent runs detect existing configuration and exit
# 0 with a quiet "already configured" line. CI verifies the config is
# set so a clone that forgot to install surfaces at first test run.
#
# Spec: ~/specs/antiek-hashimoto-engineering/sprint-e6-provenance.html

set -euo pipefail

# Resolve repo root regardless of where the script is invoked from.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
hooks_dir="$repo_root/.githooks"

if [ ! -d "$hooks_dir" ]; then
  echo "install_hooks.sh: .githooks/ not found at $hooks_dir" >&2
  echo "are you running this from inside the Antiek repo?" >&2
  exit 1
fi

# Every hook in .githooks/ must be executable. Set the bit
# idempotently; chmod is a no-op if already set correctly.
for hook in "$hooks_dir"/*; do
  if [ -f "$hook" ]; then
    chmod +x "$hook"
  fi
done

# Read current config (returns non-zero if unset → handle that).
current="$(git -C "$repo_root" config --local --get core.hooksPath || true)"

if [ "$current" = ".githooks" ]; then
  echo "install_hooks.sh: hooks already configured (core.hooksPath=.githooks)"
  exit 0
fi

if [ -n "$current" ]; then
  echo "install_hooks.sh: replacing existing core.hooksPath=$current with .githooks" >&2
fi

git -C "$repo_root" config --local core.hooksPath .githooks
echo "install_hooks.sh: configured core.hooksPath=.githooks for this clone"
echo "install_hooks.sh: hooks in .githooks/ are now active for commits in this repo"
