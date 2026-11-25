# G3.3 receipts, 2026-11-12 (Omarchy, main `b2de382`)

The gate is in `infrastructure/runbooks/boat-backbone.md` "G3.3". Decision
record `docs/decisions/boat-compute-backbone-2026-11-09.md`, owner rulings 10
and 11, and "Live evidence" run 8 interpret these files.

| Path | What it is |
|---|---|
| `run2-20261112T105855Z/g33.jsonl` | The receipt of record. One JSON line per step, ending `"pass_": true, "fails": []` |
| `run2-20261112T105855Z/service.log` | The staging service's log at INFO for `antiek` and the cascade routes (the driver's `--log-config`) |
| `run2-20261112T105855Z/boat_ledger.jsonl` | `BoatBackend`'s create ledger: three attempts, three binds |
| `run2-20261112T105855Z/console.log` | The service's stderr outside logging. It holds one note-taker boot line about a fresh state directory and nothing from Boat |
| `run1-20261112T095351Z/` | The first run, one hour earlier. Every live step passed, but its leak scan hung, so it has no `leak_scan` or `summary` line. `leak_scan_posthoc.json` is the fixed scan, run over its preserved directory |
| `scripts/g33_run.sh`, `scripts/g33_driver.py.txt` | The wrapper and driver exactly as run 2 ran them. The paths are Omarchy-local |
| `scripts/leak_scan_harness.py.txt` | Runs the driver's own `repo_fixtures` and `leak_scan` source on a directory, for the post-hoc scan and the scan's regression check |

The two Python files carry a `.txt` suffix so they stay byte-for-byte what
ran and the repository's declared ruff bar does not lint them as source.
To run one, copy it to `.py`. sha256:
- `g33_driver.py.txt`: `49ed8b4fe7f41de09f2b1df222a141a17673708e5c6b3b8f022164db7656b835`
- `g33_run.sh`: `f1e360f68d25145a487d69776eb6b006cc0aa969233994f6b2e698afd9900c94`
- `leak_scan_harness.py.txt`: `d487d171f8d09fe020c8bf6622a24097e76a5077e12bf04199cf5088b49a565b`

Every file here was scanned before it was committed. None holds a key-shaped
string or either Boat key. The temporary `ci` keys (`52ddaeb2-…` for run 1,
`83724cd4-…` for run 2) existed only in the driver's process, and both answer
401 after revocation.

Run 1's driver differs from `scripts/g33_driver.py` only in `leak_scan`.
- **Run 1:** a plain `open()` of every file under the run's directory. A FIFO
  left by the hermetic suite blocks such a read forever.
- **Now:** an `O_NONBLOCK | O_NOFOLLOW` open, and only regular files are read.
  Key-shaped strings committed at the checked-out SHA are allowed, and the
  scan has its own `try` so a summary is always written. Those committed
  strings are the suite's four synthetic fixtures.
