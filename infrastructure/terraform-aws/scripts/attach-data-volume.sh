#!/bin/bash
# Mount an EBS data volume at a fixed path, identified by its volume id.
#
# Usage: attach-data-volume VOLUME_ID MOUNTPOINT OWNER LABEL
#
# Installed by cloud-init (prod.tf, lane_host.tf) and run once per instance.
# Safe to re-run: every step checks before it acts.
#
# Why by volume id: on Nitro instances EBS volumes are NVMe devices whose
# names (nvme1n1, ...) follow probe order, not the attachment's device_name.
# The NVMe controller serial is the volume id without its hyphen, and udev
# publishes it as /dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<serial>,
# which is stable across reboots and instance types.
#
# Never reformats: mkfs runs only when blkid finds no signature at all (a
# brand-new volume). A volume restored from a snapshot, or one carrying any
# other signature, is mounted as-is or refused, never wiped.
#
# Mount-missing guard: before the first mount the mountpoint directory is
# made immutable (chattr +i). If a later boot comes up without the volume
# (fstab has nofail so the box stays reachable), writes into the bare
# directory fail instead of silently creating a second, empty state tree on
# the root disk. The systemd drop-ins written alongside this script add
# RequiresMountsFor= so the services refuse to start in that case anyway.
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 VOLUME_ID MOUNTPOINT OWNER LABEL" >&2
  exit 2
fi

volume_id="$1"
mount_dir="$2"
owner="$3"
label="$4"

case "$volume_id" in
  vol-[0-9a-f]*) ;;
  *) echo "attach-data-volume: refusing volume id '$volume_id'" >&2; exit 2 ;;
esac
case "$mount_dir" in
  /*) ;;
  *) echo "attach-data-volume: mountpoint must be absolute: '$mount_dir'" >&2; exit 2 ;;
esac

device="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_${volume_id/-/}"

# The attachment is a separate API call that can land after first boot.
for _ in $(seq 1 120); do
  [ -e "$device" ] && break
  sleep 5
done
if [ ! -e "$device" ]; then
  echo "attach-data-volume: $device did not appear within 10 minutes" >&2
  exit 1
fi

# The owner must exist before its home is created as a side effect of the
# mkdir below; otherwise useradd later finds a root-owned home it will not
# fix. setup.yml's user/group tasks are idempotent against this account.
if ! id "$owner" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --user-group "$owner"
fi

set +e
blkid -p "$device" >/dev/null 2>&1
probe=$?
set -e
case "$probe" in
  0) ;;
  2) mkfs.ext4 -q -L "$label" "$device" ;;
  *) echo "attach-data-volume: blkid probe of $device failed ($probe)" >&2; exit 1 ;;
esac

fstype="$(blkid -p -o value -s TYPE "$device" || true)"
if [ "$fstype" != "ext4" ]; then
  echo "attach-data-volume: $device carries '${fstype:-a non-filesystem signature}', expected ext4; not mounting" >&2
  exit 1
fi

mkdir -p "$mount_dir"
if ! mountpoint -q "$mount_dir"; then
  if [ -n "$(ls -A "$mount_dir")" ]; then
    echo "attach-data-volume: $mount_dir is not empty; refusing to mount over it" >&2
    exit 1
  fi
  chattr +i "$mount_dir"
fi

if ! awk -v m="$mount_dir" '$2 == m { found = 1 } END { exit !found }' /etc/fstab; then
  printf '%s %s ext4 defaults,nofail,x-systemd.device-timeout=90s 0 2\n' "$device" "$mount_dir" >> /etc/fstab
fi
systemctl daemon-reload

mountpoint -q "$mount_dir" || mount "$mount_dir"
chown "$owner:$owner" "$mount_dir"
chmod 0750 "$mount_dir"
echo "attach-data-volume: $volume_id mounted at $mount_dir"
