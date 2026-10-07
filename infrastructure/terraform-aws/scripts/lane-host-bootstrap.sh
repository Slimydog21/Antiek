#!/bin/bash
# First-boot setup of a lane host (lane_host.tf): the host half of compute's
# node contract (policy.yaml hosts.nodes + backends.node, and the helper
# bin/compute-lane-host), after cloud-init has written the config files,
# created the `compute` control account and mounted the data volume at the
# workroot. Reads /etc/default/antiek-lane-host. Idempotent: the reprovision
# path in infrastructure/runbooks/lane-host.md re-runs it.
#
# The order is chosen so that a failure part-way still leaves a host that
# stops itself:
#   0. (cloud-init runcmd, before this script) lane-host-failsafe.timer is
#      armed: unless this script reaches its last step, the host powers off
#      LANE_HOST_FAILSAFE_MINUTES after boot.
#   1. Accounts: one system user and group lane-<project> per tenant (no
#      login shell, no home); `compute` joins systemd-journal and every lane
#      group. Lanes never run as `compute`.
#   2. /etc/compute (keys directory root 0700; lane-host.json from
#      cloud-init), the workroot layout, the helper's one sudoers line
#      (checked by visudo before it is installed).
#   3. lanes.slice loaded and the sweep timer enabled. From here on,
#      compute-lane-host owns idle poweroff, the dead man and the workdir
#      TTLs, whether or not the Tailscale join below succeeds.
#   4. Host firewall: inbound only SSH on tailscale0, nothing outbound into
#      the tailnet (the Mini opens every connection; replies pass by
#      conntrack). The security group already admits nothing.
#   5. Packages (Tailscale's signed repository, rsync, nftables), then the
#      nftables table that leaves the metadata service to root only.
#   6. Tailscale join with a single-use auth key read from SSM Parameter
#      Store into a 0600 file under /run (never user_data, state, argv or the
#      journal); the parameter is deleted after a successful join.
#   7. The provisioned marker the failsafe checks.
#
# Every external wait is bounded. Any failure is logged and leaves
# /var/lib/antiek-lane-host/bootstrap-failed for the SSM check in the runbook.
#
# Never installed here: Antiek code or credentials, provider keys (the
# operator writes /etc/compute/keys/<NAME>.env), prime-agent, bd.
set -euo pipefail

# shellcheck source=/dev/null
. /etc/default/antiek-lane-host
: "${AWS_REGION:?}" "${TAILSCALE_AUTHKEY_PARAM:?}" "${TAILSCALE_HOSTNAME:?}" "${TAILSCALE_TAGS:?}"
: "${LANES_CONTROL_USER:?}" "${LANES_USER_PREFIX:?}" "${LANES_PROJECTS:?}" "${LANES_WORKROOT:?}"
: "${LANES_HELPER:?}" "${LANES_SLICE:?}"

state_dir=/var/lib/antiek-lane-host
install -d -m 0755 "$state_dir"
rm -f "$state_dir/provisioned"
on_error() {
  local rc=$? line=$1
  echo "line $line exit $rc $(date -u +%FT%TZ)" > "$state_dir/bootstrap-failed"
  logger -t lane-host-bootstrap "FAILED at line $line (exit $rc); lane-host-failsafe powers the host off ${LANE_HOST_FAILSAFE_MINUTES:-60} min after boot"
}
trap 'on_error $LINENO' ERR

systemd_version="$(systemctl --version | awk 'NR == 1 { print $2 }')"
if [ "${systemd_version:-0}" -lt 254 ]; then
  echo "lane-host-bootstrap: systemd $systemd_version < 254 (compute needs --expand-environment)" >&2
  exit 1
fi

# ── 1. accounts ──────────────────────────────────────────────────────────────
read -r -a projects <<< "$LANES_PROJECTS"
control_groups=(systemd-journal)
for p in "${projects[@]}"; do
  u="${LANES_USER_PREFIX}${p}"
  getent group "$u" >/dev/null || groupadd --system "$u"
  id -u "$u" >/dev/null 2>&1 \
    || useradd --system --gid "$u" --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$u"
  control_groups+=("$u")
done
usermod -aG "$(IFS=,; echo "${control_groups[*]}")" "$LANES_CONTROL_USER"

# ── 2. /etc/compute, workroot, helper + sudoers ─────────────────────────────
install -d -o root -g root -m 0755 /etc/compute
install -d -o root -g root -m 0700 /etc/compute/keys
chown root:root /etc/compute/keys
chmod 0700 /etc/compute/keys
python3 -c 'import json, sys; json.load(open(sys.argv[1]))' /etc/compute/lane-host.json

if [ "$(stat -c %U:%a "$LANES_HELPER")" != "root:755" ] || [ "$(head -c 18 "$LANES_HELPER")" != "#!/usr/bin/python3" ]; then
  echo "lane-host-bootstrap: $LANES_HELPER is not the root-owned compute helper" >&2
  exit 1
fi

if ! mountpoint -q "$LANES_WORKROOT"; then
  echo "lane-host-bootstrap: $LANES_WORKROOT is not mounted" >&2
  exit 1
fi
chown root:root "$LANES_WORKROOT"
chmod 0755 "$LANES_WORKROOT"
for p in "${projects[@]}"; do
  u="${LANES_USER_PREFIX}${p}"
  install -d -o "$u" -g "$u" -m 2770 "$LANES_WORKROOT/$p"
  chown "$u:$u" "$LANES_WORKROOT/$p"
  chmod 2770 "$LANES_WORKROOT/$p"
done
# Exit records (a root ExecStopPost writes them) and the dispatcher's
# heartbeats: writable by the control account, unreadable by lanes.
install -d -o "$LANES_CONTROL_USER" -g "$LANES_CONTROL_USER" -m 0750 "$LANES_WORKROOT/.records"

sudoers_tmp="$(mktemp)"
printf '%s ALL=(root) NOPASSWD: %s\n' "$LANES_CONTROL_USER" "$LANES_HELPER" > "$sudoers_tmp"
visudo -cqf "$sudoers_tmp"
install -o root -g root -m 0440 "$sudoers_tmp" /etc/sudoers.d/compute-lane-host
rm -f "$sudoers_tmp"

# ── 3. lanes.slice + the sweep (idle poweroff, dead man, TTLs) ──────────────
systemctl daemon-reload
systemctl start "$LANES_SLICE"
if [ "$(systemctl show -p MemoryMax --value "$LANES_SLICE")" = "infinity" ]; then
  echo "lane-host-bootstrap: $LANES_SLICE has no MemoryMax" >&2
  exit 1
fi
systemctl enable --now compute-lane-host-sweep.timer

# ── 4. firewall ──────────────────────────────────────────────────────────────
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0 to any port 22 proto tcp
ufw deny out on tailscale0
ufw --force enable

# ── 5. packages, metadata service for root only ─────────────────────────────
# shellcheck source=/dev/null
codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
timeout 120 curl -fsSL --retry 3 "https://pkgs.tailscale.com/stable/ubuntu/${codename}.noarmor.gpg" \
  -o /usr/share/keyrings/tailscale-archive-keyring.gpg
timeout 120 curl -fsSL --retry 3 "https://pkgs.tailscale.com/stable/ubuntu/${codename}.tailscale-keyring.list" \
  -o /etc/apt/sources.list.d/tailscale.list
timeout 600 apt-get update -q
DEBIAN_FRONTEND=noninteractive timeout 900 apt-get install -y -q tailscale rsync nftables
systemctl enable --now tailscaled
systemctl enable --now imds-root-only.service

# ── 6. Tailscale ─────────────────────────────────────────────────────────────
if tailscale status >/dev/null 2>&1; then
  echo "lane-host-bootstrap: already joined the tailnet; not re-authenticating"
else
  timeout 300 snap wait system seed.loaded
  snap list aws-cli >/dev/null 2>&1 || timeout 600 snap install aws-cli --classic

  umask 077
  keyfile="$(mktemp /run/tailscale-authkey.XXXXXX)"
  trap 'rm -f "$keyfile"' EXIT
  timeout 120 /snap/bin/aws ssm get-parameter \
    --region "$AWS_REGION" \
    --name "$TAILSCALE_AUTHKEY_PARAM" \
    --with-decryption \
    --query Parameter.Value \
    --output text > "$keyfile"
  if [ ! -s "$keyfile" ]; then
    echo "lane-host-bootstrap: SSM parameter $TAILSCALE_AUTHKEY_PARAM is empty" >&2
    exit 1
  fi
  # --accept-dns=false: the host never resolves tailnet names (the Mini
  # opens every connection), and outbound into tailscale0 is denied above.
  tailscale up \
    --auth-key="file:$keyfile" \
    --hostname="$TAILSCALE_HOSTNAME" \
    --advertise-tags="$TAILSCALE_TAGS" \
    --accept-dns=false \
    --timeout=5m
  rm -f "$keyfile"
  # Single use: once joined, nothing on any instance can read the key again.
  timeout 120 /snap/bin/aws ssm delete-parameter --region "$AWS_REGION" --name "$TAILSCALE_AUTHKEY_PARAM" \
    || logger -t lane-host-bootstrap "warning: could not delete $TAILSCALE_AUTHKEY_PARAM; delete it by hand (lane-host.md)"
fi

# ── 7. done ──────────────────────────────────────────────────────────────────
rm -f "$state_dir/bootstrap-failed"
date -u +%FT%TZ > "$state_dir/provisioned"
echo "lane-host-bootstrap: done ($(tailscale ip -4 2>/dev/null | head -n1))"
