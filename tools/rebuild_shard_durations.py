#!/usr/bin/env python3
"""Rebuild `pytest_shard_durations.json` from real CI logs.

WHY THIS EXISTS
---------------
`tools/pytest_file_shard.py` packs test files into shards with longest-processing-time
bin packing, weighted by the per-file seconds in `pytest_shard_durations.json`. That
map was hand-refreshed, and measured against this repository it is wrong in BOTH
directions:

    tests/test_knowledge_reuse_spr06.py    recorded 349.0s   actually   6.1s   57x high
    tests/test_merge_staging.py            recorded 144.0s   actually   ~21s    6.9x high
    tests/test_thought_partner_account...   recorded  83.9s   actually   ~89s    accurate

A uniform scale error would be harmless -- LPT is scale-invariant, which is why the
suite-wide ~2.4x understatement never broke the balance. An INCONSISTENT one is not:
a file recorded at 349s when it costs 6s gets the largest weight in the suite, is
given a shard to itself, and the other three shards carry the difference.

WHERE THE NUMBERS COME FROM
---------------------------
CI runs the shards with `-v`, which prints each node id as it STARTS. The log lines
carry millisecond timestamps, so the interval between one test starting and the next
starting is the first test's duration. Aggregated per file, that is a real,
contemporaneous measurement from the same machine the shards actually run on --
strictly better evidence than a pasted local run.

The last test of each shard has no successor and is therefore unmeasured; it is left
out rather than guessed.

USAGE
-----
    gh run view <run-id> -R <owner>/<repo> --log --job <shard-job-id> > shard0.log
    ... once per shard ...
    python3 tools/rebuild_shard_durations.py --out tools/pytest_shard_durations.json \
        shard0.log shard1.log shard2.log shard3.log

Add `--check` to compare against the committed map and report the worst offenders
without writing anything.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(tests/\S+?)::(\S+)")


def parse_log(path: Path) -> list[tuple[float, str]]:
    """[(seconds_since_epoch, source_file)] in the order pytest printed them."""
    import datetime as _dt

    out: list[tuple[float, str]] = []
    for raw in path.read_text(errors="replace").splitlines():
        content = _ANSI.sub("", raw).rstrip("\n").split("\t")[-1]
        m = _LINE.match(content)
        if not m:
            continue
        stamp, source_file = m.group(1), m.group(2)
        # GitHub writes seven fractional digits; strptime accepts six.
        stamp = re.sub(r"(\.\d{6})\d*Z$", r"\1Z", stamp)
        when = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=_dt.timezone.utc)
        out.append((when.timestamp(), source_file))
    return out


def durations_from_logs(paths: list[Path]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for path in paths:
        seq = parse_log(path)
        for (t0, f0), (t1, _f1) in zip(seq, seq[1:]):
            delta = t1 - t0
            # Guard against out-of-order or duplicated lines rather than
            # accumulating nonsense into a weight the packer trusts.
            if 0.0 < delta < 3600.0:
                totals[f0] = totals.get(f0, 0.0) + delta
        print(f"  {path.name}: {len(seq)} test lines, {len({f for _, f in seq})} files", file=sys.stderr)
    return {k: round(v, 3) for k, v in sorted(totals.items())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("tools/pytest_shard_durations.json"))
    ap.add_argument("--check", action="store_true", help="report against the committed map, write nothing")
    args = ap.parse_args(argv)

    fresh = durations_from_logs(args.logs)
    if not fresh:
        print("no test lines found — refusing to write an empty map", file=sys.stderr)
        return 1

    total = sum(fresh.values())
    print(f"measured {len(fresh)} files, {total / 60:.1f} minutes of test time", file=sys.stderr)

    existing: dict[str, float] = {}
    if args.out.exists():
        try:
            existing = {k: float(v) for k, v in json.loads(args.out.read_text()).items()}
        except Exception:
            existing = {}

    if existing:
        common = [f for f in fresh if f in existing and existing[f] > 0]
        worst = sorted(common, key=lambda f: abs(fresh[f] / existing[f] - 1.0), reverse=True)[:8]
        print("\nlargest disagreements (new vs recorded):", file=sys.stderr)
        for f in worst:
            ratio = fresh[f] / existing[f]
            print(f"  {ratio:7.2f}x  {fresh[f]:8.1f}s vs {existing[f]:8.1f}s  {f}", file=sys.stderr)

    if args.check:
        return 0

    args.out.write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out} ({len(fresh)} files)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
