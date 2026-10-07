#!/bin/bash
# Power the lane host off after LANES_IDLE_STOP_MINUTES with no lane work.
#
# Runs every 5 minutes from lanes-idle-stop.timer. The instance is created
# with instance_initiated_shutdown_behavior = "stop", so poweroff STOPS it:
# compute and its auto-assigned public IPv4 stop billing, the EBS volumes
# keep billing, and the operator (or a later dispatcher step) starts it
# again with `aws ec2 start-instances`. This is the "stop when idle" half of
# the operator's USD 250/month approval; the budget action is the hard cap.
#
# Busy means either of:
#   - any process in the lanes user's lanes.slice cgroup. Every lane is a
#     transient user unit there (compute 1.6.0: systemd-run --user
#     --slice=lanes.slice), so this counts running lanes directly;
#   - a logind session: the dispatcher's ssh polls, stage-in/out rsyncs and
#     operator shells each hold one while they run.
#
# The last-busy stamp lives under /run (tmpfs), so every boot starts a fresh
# idle window instead of powering off on the first tick after a start.
set -euo pipefail

# The overrides below exist only so tests/test_terraform_aws_invariants.py
# can run this script against a fake cgroup tree and stub binaries.
# shellcheck source=/dev/null
. "${LANE_HOST_DEFAULTS:-/etc/default/antiek-lane-host}"
limit="${LANES_IDLE_STOP_MINUTES:-0}"
[ "$limit" -gt 0 ] || exit 0

state_dir="${LANES_IDLE_STATE_DIR:-/run/lanes-idle}"
mkdir -p "$state_dir"
now="$(date +%s)"

uid="${LANES_UID:-$(id -u "${LANES_USER:-lanes}")}"
slice_dir="${LANES_CGROUP_ROOT:-/sys/fs/cgroup}/user.slice/user-$uid.slice/user@$uid.service/lanes.slice"
procs=0
if [ -d "$slice_dir" ]; then
  procs="$(find "$slice_dir" -name cgroup.procs -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')"
fi
sessions="$(loginctl list-sessions --no-legend 2>/dev/null | wc -l | tr -d ' ')"

if [ "$procs" -gt 0 ] || [ "$sessions" -gt 0 ] || [ ! -f "$state_dir/last-busy" ]; then
  echo "$now" > "$state_dir/last-busy"
  exit 0
fi

idle_min=$(( (now - $(cat "$state_dir/last-busy")) / 60 ))
if [ "$idle_min" -ge "$limit" ]; then
  logger -t lanes-idle-stop "no lane process and no login session for ${idle_min} min (limit ${limit}); powering off, the instance stops"
  systemctl poweroff
fi
