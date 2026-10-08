#!/bin/bash
# Power the lane host off when, LANE_HOST_FAILSAFE_MINUTES after a boot, it
# is not in a state that can ever stop itself:
#   - the bootstrap never finished (no provisioned marker: a first boot that
#     failed or hung, e.g. the Tailscale key was missing or expired);
#   - the workroot is not mounted (the data volume did not attach this boot);
#   - compute-lane-host-sweep.timer is not active.
#
# This is not idle stop. Idle poweroff has exactly one owner, compute's
# helper (`compute-lane-host sweep`, idle_poweroff_min); this unit covers the
# boots on which that owner cannot run. Without it an unreachable host (no
# inbound rule, never joined the tailnet) bills ~USD 200/month, below the
# lane-host cap, with nothing to stop it.
#
# Runs once per boot from lane-host-failsafe.timer, which cloud-init arms
# before any step that can fail. To keep a broken host up while debugging it
# over SSM: `sudo systemctl stop lane-host-failsafe.timer` (this boot only).
set -uo pipefail

# The overrides exist only so tests/test_terraform_aws_invariants.py can run
# this script against a temporary directory and stub binaries.
# shellcheck source=/dev/null
. "${LANE_HOST_DEFAULTS:-/etc/default/antiek-lane-host}"
state_dir="${LANE_HOST_STATE_DIR:-/var/lib/antiek-lane-host}"
workroot="${LANES_WORKROOT:-/srv/lanes}"

why=()
[ -f "$state_dir/provisioned" ] || why+=("the bootstrap never completed")
mountpoint -q "$workroot" || why+=("$workroot is not mounted")
systemctl is-active --quiet compute-lane-host-sweep.timer || why+=("compute-lane-host-sweep.timer is not active")

if [ "${#why[@]}" -eq 0 ]; then
  exit 0
fi
msg="$(IFS=';'; echo "${why[*]}")"
logger -t lane-host-failsafe "powering off: $msg"
echo "lane-host-failsafe: powering off: $msg" >&2
systemctl poweroff
