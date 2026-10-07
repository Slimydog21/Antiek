#!/bin/bash
# First-boot setup of a lane host (lane_host.tf), after cloud-init has
# created the `lanes` account and mounted the data volume at /srv/lanes.
# Reads /etc/default/antiek-lane-host. Safe to re-run.
#
# What it does, in order:
#   1. The compute 1.6.0 host contract for the lanes account: a lingering
#      user manager (so user units run with nobody logged in), the user
#      lanes.slice that caps every lane together, ~/.config/compute/ for
#      the per-node key file, and the workroot owned by lanes. It then
#      checks that memory, pids and cpu are delegated to the user manager
#      and fails loudly if not: per-lane MemoryMax would otherwise be
#      silently unenforced.
#   2. Host firewall: deny inbound except SSH on tailscale0. The security
#      group already admits nothing; this is the second layer.
#   3. Tailscale from its signed apt repository (plus rsync for stage-in
#      and stage-out), then joins the tailnet with an auth key read at boot
#      from SSM Parameter Store (SecureString). The key is never in
#      user_data, Terraform state, argv or the journal: it is fetched into a
#      0600 file under /run (tmpfs) and passed as file:PATH.
#   4. The idle-stop timer, when enabled.
#
# What it never does: install Antiek code or any Antiek credential (D-18 /
# D-19). The per-node provider keys and prime-agent are the operator's
# later steps (infrastructure/runbooks/lane-host.md).
set -euo pipefail

# shellcheck source=/dev/null
. /etc/default/antiek-lane-host
: "${AWS_REGION:?}" "${TAILSCALE_AUTHKEY_PARAM:?}" "${TAILSCALE_HOSTNAME:?}" "${TAILSCALE_TAGS:?}"
: "${LANES_USER:?}" "${LANES_WORKROOT:?}" "${LANES_SLICE_MEMORY_HIGH:?}" "${LANES_SLICE_MEMORY_MAX:?}" "${LANES_SLICE_TASKS_MAX:?}"

# ── 1. lanes account: workroot, key dir, user slice, linger, delegation ─────
lanes_home="$(getent passwd "$LANES_USER" | cut -d: -f6)"
lanes_uid="$(id -u "$LANES_USER")"
[ -n "$lanes_home" ] || { echo "lane-host-bootstrap: no home for $LANES_USER" >&2; exit 1; }

install -d -o "$LANES_USER" -g "$LANES_USER" -m 0750 "$LANES_WORKROOT"
for d in .config .config/systemd .config/systemd/user .config/compute; do
  install -d -o "$LANES_USER" -g "$LANES_USER" -m 0700 "$lanes_home/$d"
done

slice="$lanes_home/.config/systemd/user/lanes.slice"
cat > "$slice.tmp" <<EOF
# lane-host-bootstrap (infrastructure/terraform-aws). Every compute lane is
# a transient user unit in this slice; these limits cap them together.
# Per-lane limits come from the compute policy on each systemd-run.
[Unit]
Description=compute lanes (systemd-run --user --slice=lanes.slice)

[Slice]
MemoryAccounting=yes
MemoryHigh=$LANES_SLICE_MEMORY_HIGH
MemoryMax=$LANES_SLICE_MEMORY_MAX
TasksAccounting=yes
TasksMax=$LANES_SLICE_TASKS_MAX
CPUAccounting=yes
EOF
chown "$LANES_USER:$LANES_USER" "$slice.tmp"
chmod 0644 "$slice.tmp"
mv -f "$slice.tmp" "$slice"

systemctl daemon-reload
loginctl enable-linger "$LANES_USER"
for _ in $(seq 1 30); do
  systemctl is-active --quiet "user@$lanes_uid.service" && break
  sleep 1
done

controllers="/sys/fs/cgroup/user.slice/user-$lanes_uid.slice/user@$lanes_uid.service/cgroup.controllers"
for c in memory pids cpu; do
  if ! grep -qw "$c" "$controllers" 2>/dev/null; then
    echo "lane-host-bootstrap: controller '$c' is not delegated to user@$lanes_uid.service ($controllers)" >&2
    exit 1
  fi
done
# The user manager loads lanes.slice on first reference anyway; the reload
# only matters on a re-run that changed the limits.
runuser -u "$LANES_USER" -- env XDG_RUNTIME_DIR="/run/user/$lanes_uid" systemctl --user daemon-reload \
  || echo "lane-host-bootstrap: warning: user daemon-reload failed; lanes.slice loads on first use" >&2

# ── 2. firewall ──────────────────────────────────────────────────────────────
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0 to any port 22 proto tcp
ufw --force enable

# ── 3. Tailscale (+ rsync), join the tailnet ────────────────────────────────
# shellcheck source=/dev/null
codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${codename}.noarmor.gpg" \
  -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${codename}.tailscale-keyring.list" \
  -o /etc/apt/sources.list.d/tailscale.list
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q tailscale rsync
systemctl enable --now tailscaled

if tailscale status >/dev/null 2>&1; then
  echo "lane-host-bootstrap: already joined the tailnet; not re-authenticating"
else
  snap wait system seed.loaded
  snap list aws-cli >/dev/null 2>&1 || snap install aws-cli --classic

  umask 077
  keyfile="$(mktemp /run/tailscale-authkey.XXXXXX)"
  trap 'rm -f "$keyfile"' EXIT
  /snap/bin/aws ssm get-parameter \
    --region "$AWS_REGION" \
    --name "$TAILSCALE_AUTHKEY_PARAM" \
    --with-decryption \
    --query Parameter.Value \
    --output text > "$keyfile"
  if [ ! -s "$keyfile" ]; then
    echo "lane-host-bootstrap: SSM parameter $TAILSCALE_AUTHKEY_PARAM is empty" >&2
    exit 1
  fi
  tailscale up \
    --auth-key="file:$keyfile" \
    --hostname="$TAILSCALE_HOSTNAME" \
    --advertise-tags="$TAILSCALE_TAGS"
  rm -f "$keyfile"
fi

# ── 4. idle stop ─────────────────────────────────────────────────────────────
if [ "${LANES_IDLE_STOP_MINUTES:-0}" -gt 0 ]; then
  systemctl enable --now lanes-idle-stop.timer
fi
echo "lane-host-bootstrap: done ($(tailscale ip -4 2>/dev/null | head -n1))"
