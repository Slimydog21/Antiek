# Encrypted critical-state backup and offline recovery

This extends the existing DuckDB export, normalization, import/count/catalog
verification, writer flock, restart guard and downloaded-object hash check.
It does not replace those checks or alter `runtime/db_lock.py`.

The job refuses a missing or unsafe required source, missing recipient,
incoherent BYOK pair, invalid SQLite snapshot, upload failure or either
read-back failure. It does not stamp a new freshness marker on those failures.
There is no plaintext-upload fallback. Configure and prove recovery before
Root deploys this backup change. A green unit suite is not production recovery
or independent key custody.

## Recovery-key custody before deployment

Root must provision a dedicated Curve25519 recovery identity on a trusted
recovery computer, outside the production host and backup bucket. The private
identity is exactly 32 bytes encoded as 64 hex characters, optionally followed
by one newline, in an owned `0600` file. The corresponding public recipient has
the same encoding. Use the existing PyNaCl dependency to generate this pair on
the recovery computer. Do not print the private identity or send it through an
agent transcript, command argument, receipt, commit or PR.

Keep at least two independently accessible protected copies of the private
identity according to Root's recovery custody policy. Record custodians,
storage locations and the SHA-256 fingerprint of the public recipient without
recording private bytes. Demonstrate recovery from a custody copy, not just a
key still loaded on the generating computer. Deploy only the public recipient
to `/etc/antiek/backup-recovery-public.hex`, owned by root and mode `0600`.
Never put the recovery private identity on the source host or in either backup
object. A missing custody decision or unavailable identity blocks readiness.

Encryption uses existing libsodium primitives through PyNaCl. SealedBox wraps
a fresh secretstream key for the recovery recipient; XChaCha20-Poly1305
authenticates ordered 64 KiB frames, the envelope and an explicit final frame.
The container starts with `ANTIEK-CRITICAL-BACKUP\0v1\n`. Truncation, appended
data, wrong keys and modified frames refuse recovery. This versioned container
is Antiek's format, not an age-compatible file. SealedBox is anonymous-sender
encryption: anyone with the public recipient can construct a new object.
Keep trusted object identities/digests outside the bucket; encryption alone
does not prove who created an archive or prevent replay of an older archive.
These controls do not protect against root on the live source host.

Failed publication, including an interruption after the native link is acquired,
retires only the new output inode. A file replaced by another writer is retained.
If that owned cleanup itself fails, the helper refuses with an explicit incomplete
cleanup error; reconcile the private staging state before continuing recovery.
Snapshot, preparation and offline restore also clean their owned staging on a
Python interruption, then re-raise it. Failed native cleanup remains incomplete;
this does not guarantee cleanup after forced termination or host failure.

## Source inventory and configuration

Root owns the production inventory. Do not infer it from an account/email or
read production secrets during source preparation. Write the confirmed paths
to a root-owned `0600` `/etc/antiek/backup-critical-sources.json`. The exact
version-1 schema is:

```json
{
  "version": 1,
  "state": "/home/antiek/.antiek",
  "byok_key": "/home/antiek/.antiek/byok/byok_master.key",
  "byok_artifact": "/home/antiek/.antiek/byok/credentials.enc",
  "accounts": "/home/antiek/.antiek/auth/accounts.json",
  "passkeys": "/home/antiek/.antiek/auth/passkeys.json",
  "settings": ["/home/antiek/.antiek/settings"],
  "turbopuffer": "/home/antiek/.antiek/turbopuffer-shadow",
  "system_files": {
    "secrets.env": "/etc/antiek/secrets.env",
    "rclone.conf": "/etc/rclone/rclone.conf",
    "tunnel.json": "/etc/cloudflared/CONFIRMED-TUNNEL-ID.json"
  },
  "extra_sqlite": []
}
```

This is a shape example, not a statement that these files currently exist.
The tunnel ID and every configured override must be confirmed by Root. The
state path must equal the deployed template's state directory. Paths must be
absolute without traversal. Sources and parents must have the admitted
root/Antiek ownership and protected permissions; links, hard-linked files,
special files and mutable parents refuse. Required key, ciphertext, account,
passkey and system-configuration files must have distinct paths; reusing one
source for two required roles refuses before staging. Source files may be `0640` for the
root/Antiek group, but may not be world-accessible or group-writable. Snapshot
files are `0600`, directories `0700`. Bounds are 32,768 inspected entries,
8 GiB per ledger/file and 16 GiB total critical-state payload. Settings and
ordinary configuration files have a 16 MiB read bound. Crossing a limit is a
failed backup, not silently omitted coverage.

The current source resolves these durable paths independently:

| Store | Confirmed source contract to reconcile |
| --- | --- |
| BYOK | `ANTIEK_BYOK_KEY_FILE` and `ANTIEK_BYOK_ARTIFACT`; key/artifact sidecar flocks in `runtime/byok/store.py` |
| Accounts | `ANTIEK_ACCOUNT_STORE`; otherwise the auth account store under the configured state/home |
| Passkeys | `ANTIEK_PASSKEY_STORE`; otherwise the service user's `~/.antiek/auth/passkeys.json` |
| Research spend | `ANTIEK_RESEARCH_SPEND_DB`; otherwise `<graph filename>.research-spend.sqlite3` |
| BYOT usage | `ANTIEK_BYOT_USAGE_DB`; otherwise `<spend filename>.byot-usage.sqlite3` |
| Owner launches | `ANTIEK_OWNER_LAUNCH_DB`; otherwise the event-root sidecar `owner-launches.sqlite3` |
| Research intents | `research-intents.sqlite3` under its configured state root |
| Tool search | `settings/research_tool_search.sqlite3` under its resolved root |
| Preferences and other ledgers | Telemetry preferences, advertiser, twin/segmentation and DuckLake SQLite stores use their actual configured/caller paths |
| TurboPuffer | `ANTIEK_TURBOPUFFER_MANIFEST_DIR`, including its current promote pointer |
| Settings | Include every actual settings directory; do not assume all callers resolve `ANTIEK_HOME` identically |

Automatic SQLite discovery inspects bounded metadata under the configured state
directory. It does not read ordinary non-ledger file contents. It excludes only
the fixed real owned `cache/sentence-transformers` directory, which contains
reconstructible model blobs and snapshot links. It records the exclusion and
whether that directory was observed in the manifest; excluded descendants are
not enumerated or backed up. A symlink instead of that directory, a symlink in
another cache subtree, or any outside-cache symlink still refuses discovery.
Other cache siblings and state directories remain traversed, including writable
directories that are not themselves admitted durable sources.

Every discovered `.sqlite`, `.sqlite3` and `.db` ledger still passes the unchanged
strict file and parent admission before a source-owner worker opens it. Discovery
of a `0644` database or a database under a `0775` parent does not admit its bytes.
Root must reconcile those actual permissions before deployment; this source change
does not chmod or chown live state. Required settings, keys, accounts, passkeys and
configuration continue to use strict traversal and admission, without cache waivers.

List all active SQLite paths outside the configured state root, or with other
filenames, explicitly in `extra_sqlite`. Every explicitly named ledger goes
through SQLite online backup and integrity checking regardless of its suffix or
the automatic model-cache exclusion. No configurable arbitrary exclusions exist.
Root must confirm the complete active-store inventory before readiness;
bounded state traversal is not a global store census. A link anywhere in an
included tree refuses rather than following or silently omitting it. If a
derived cache prevents traversal, return that exact inventory conflict instead
of waiving coverage. Required stores are not silently created when absent.

BYOK snapshots open the original sidecar locks read-only, hold the existing
key lock followed by the artifact lock and
authenticate every existing credential with the captured key. The raw master
key is staged outside the data archive, encrypted into a separate object and
removed before tar creation. The data archive carries only its ciphertext and
the separate encrypted object's digest. SQLite online backup includes committed
WAL data without copying live `-wal`/`-shm` files. A readonly SQLite connection
can still create live sidecars. Each SQLite snapshot therefore runs in a
bounded worker under the source file's actual Unix UID/GID; a root collector
clears supplementary groups and changes ownership only of its new private
staging directory. It never chowns a live database or sidecar. The worker
checks its UID before opening SQLite, and the collector directly waits for
completion or retires that owned child before refusing. Synthetic controls
exercise the same-user native worker; production root-to-application privilege
drop, interpreter access and sandbox compatibility remain deployment checks.
Independent stores have
different snapshot times; this is not a cross-store transaction.

The systemd unit reads optional `/etc/antiek/backup.env` for these path-only
settings:

```text
ANTIEK_BACKUP_CRITICAL_CONFIG=/etc/antiek/backup-critical-sources.json
ANTIEK_BACKUP_RECIPIENT_FILE=/etc/antiek/backup-recovery-public.hex
ANTIEK_BACKUP_REMOTE_PREFIX=r2:antiek-backups/nightly/encrypted-v1
```

Root must use the existing actual R2 bucket. The prefix override supports a
staging namespace without creating a bucket. No AWS migration, account action,
retention deletion or provider spend is part of this change. The recipient
file and inventory must be readable inside the existing systemd sandbox;
BYOK sidecar locks must already exist and be readable. A missing lock refuses
without creating root-owned application state. SQLite source-owner workers
need the existing admitted ledger directories writable for native WAL/SHM
creation, and must be able to execute the deployed interpreter and helper.
An external-store sandbox conflict must be resolved explicitly, not by a broad
`ReadWritePaths` relaxation.

## Off-box object contract

Each successful job creates two independently authenticated objects under the
configured prefix:

- `antiek-TIMESTAMP.tar.gz`, the encrypted data container. Its historical
  logical basename remains compatible with the existing freshness parser;
  it is **not plaintext gzip** in the `encrypted-v1` namespace.
- `antiek-TIMESTAMP.byok-key.enc`, the separately encrypted 32-byte BYOK key.

Neither contains the recovery private identity. Both upload and downloaded
SHA-256 verification must succeed before the marker advances. The marker adds
the encrypted contract version, encryption format, separate key remote/digest,
public recipient fingerprint and per-store consistency qualification. Existing
DuckDB counts and restart/freshness requirements remain. Transfer stderr stays
in private staging and is removed on all exits; logs report phase and refusal,
not provider credentials. Cleanup is ordinary unlink/removal, not guaranteed
secure erasure on SSDs, snapshots or a compromised host.

Do not delete old plaintext backups automatically. Root must separately address
their confidentiality, access and retention. Preserve the last recoverable
generation until a new encrypted generation has been recovered off host.

## Offline restore drill

Root selects a trusted paired generation using custody records and compares
both downloaded digests. Place encrypted objects and the independently
recovered identity in a private recovery directory. Use the matching reviewed
application version and its existing dependencies. Invoke:

```bash
python -m tools.critical_state_backup restore \
  --data /PRIVATE/antiek-TIMESTAMP.tar.gz \
  --key /PRIVATE/antiek-TIMESTAMP.byok-key.enc \
  --identity /INDEPENDENT-CUSTODY/recovery-private.hex \
  --destination /PRIVATE/NEW-OFFLINE-RECOVERY
```

The destination must be absent. Recovery authenticates both streams, rejects
tar traversal, links, devices, duplicate members and excessive sizes, verifies
the exact critical file inventory/hashes and archive/key pairing, and decrypts
every BYOK credential with the recovered key. It produces private plaintext in
an offline directory only. It never overwrites live state or starts services.
The recovered BYOK key remains in `separate-byok-key/byok_master.key`, outside
`critical-state`, until Root performs the controlled restore.

After this drill, follow the existing disaster-recovery DuckDB pre-IMPORT,
catalog/count and single-writer procedure. Validate each SQLite snapshot with
its real schema and application invariants, restore permissions/ownership, and
join the recorded source-path map to the receiver. Reconcile account aliases
and passkey state before authentication is resumed. Confirm settings and the
TurboPuffer pointer against the actual configured namespaces.

DR access is privileged operational custody, not a normal user's account.
The helper does not recover pending magic-link claims, passkey challenges or
session-cookie jars. Restored signing secrets, passkeys and job ledgers still
require a deliberate cutover policy: retire outstanding sessions/challenges,
fence old jobs/leases and invalidate stale grants before serving. Restoring
bytes does not authorize provider calls or resurrect a job. Record the tested
generation, object digests, recipient fingerprint, owner/custody approvals,
actual restore results and remaining gaps without secret values. Readiness
requires this actual off-host drill; synthetic tests alone cannot certify it.
