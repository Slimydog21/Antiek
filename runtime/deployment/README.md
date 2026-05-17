# runtime/deployment/

VPS bootstrap, systemd units, backup scripts.

## Target

VPS (Hetzner, DigitalOcean, equivalent) with 16–32 CPU cores,
64–128 GB RAM, 1–2 TB NVMe storage. Estimated cost: $200–400/month.

## Files (planned)

- `bootstrap.sh` — fresh-VPS bring-up. Installs Docker, pulls images,
  brings up the compose stack.
- `systemd/` — service units for the host-level processes (the
  DuckDB warden, the heartbeat).
- `backup.sh` — nightly backup of `~/.antiek/` to S3-compatible
  storage (Backblaze B2 or Wasabi for cost). The event log is the
  recoverable source of truth; the DuckDB file can be reconstructed
  by replaying events.
- `restore.sh` — documented restore procedure.

## Local backends

No local-model-hosting in this build. The dispatch router has the
abstraction in place; adding a local backend is one new entry in
`substrate/dispatch/config.yaml` and one new module behind the same
interface.
