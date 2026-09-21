# runtime/deployment/

VPS bootstrap, systemd units, backup scripts.

## Target

VPS (Hetzner, DigitalOcean, equivalent) with 16–32 CPU cores,
64–128 GB RAM, 1–2 TB NVMe storage. Estimated cost: $200–400/month.

## Files (IMPLEMENTED — not here)

The deployment artifacts are real and canonical in `infrastructure/`:

- `infrastructure/ansible/playbooks/setup.yml` — fresh-VPS bring-up
  (idempotent; installs substrate, Caddy, systemd units, rclone,
  backup cron).
- `infrastructure/ansible/templates/` — the systemd units and timers
  (`antiek.service`, `antiek-backup.{service,timer}`,
  `antiek-health-probe.*`, `antiek-arxiv-oai-sync.*`), Caddy config,
  and `backup.sh.j2` (DuckDB `EXPORT DATABASE` consistent snapshot +
  append-only event-log rsync + R2 upload with in-script retention).
- `infrastructure/ansible/playbooks/deploy.yml`, `backup.yml` — deploy
  and ad-hoc backup runs.
- `infrastructure/runbooks/first-deploy.md` and
  `infrastructure/runbooks/disaster-recovery.md` — the step-by-step
  bring-up and restore procedures (RPO 24h / RTO ~30min).

If you are looking for "the backup script" or "the systemd units",
they render from those templates — do not duplicate them here.

## Local backends

No local-model-hosting in this build. The dispatch router has the
abstraction in place; adding a local backend is one new entry in
`substrate/dispatch/config.yaml` and one new module behind the same
interface.
