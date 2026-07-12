# runtime/deployment/

VPS bootstrap, systemd units, backup scripts.

## Target

VPS (Hetzner, DigitalOcean, equivalent) with 16–32 CPU cores,
64–128 GB RAM, 1–2 TB NVMe storage. Estimated cost: $200–400/month.

## Files

- `bootstrap.sh` — fresh-VPS bring-up. Installs Docker, pulls images,
  brings up the compose stack.
- `systemd/antiek-midnight-oil-api.service` — explicit spend-authoritative API
  factory. The default `interfaces.research.api.app:app` remains non-spending.
- `systemd/antiek-midnight-oil-worker.service` — one durable queue consumer;
  claim, deposit, graph projection, and terminal archive share one config.
- `midnight-oil.runtime.example.json` — secret-free closed configuration.
- `provider-attestation.example.json` — shape of the operator evidence record
  required before any endpoint is marked idempotent. Generate its
  `endpoint_sha256` with
  `substrate.midnight_oil.runtime.provider_endpoint_sha256`; copying the
  placeholder never enables spend.

Install the production virtualenv with the embedding extra before enabling the
units (`uv sync --extra embedding`). Copy neither example verbatim: runtime
loading requires absolute real paths, base64url consent keys in the named
environment variables, an exact SHA-256 of the deployed dispatch config, and a
provider idempotency evidence reference. Start the API and worker only after
`uv run antiek midnight-oil-worker --help` resolves from the installed project.
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
