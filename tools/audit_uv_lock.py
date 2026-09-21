"""Audit uv.lock against OSV.

WHY THIS EXISTS. dep_audit scanned the manifests someone thought to NAME:
tools/lints/constraints.txt (the CI lock) and apps/reading/package-lock.json.
`uv.lock` — 194 pinned packages, committed to main — was named by nothing, so
no gate looked at it for months. When Dependabot alerts were finally switched
on it reported 18 alerts there including a CRITICAL, and `anyio` sat at the
vulnerable 4.14.1 while constraints.txt had already been fixed to 4.14.2.

WHY OSV RATHER THAN pip-audit. `pip-audit -r` dry-run-INSTALLS the
requirements even with --no-deps, so it dies on platform-specific pins that
cannot resolve on the runner (`cuda-bindings`, the nvidia-* wheels). OSV's
querybatch API takes name+version and needs no resolution, which is the right
shape for auditing a cross-platform lockfile.
"""

from __future__ import annotations

import json
import sys
import tomllib
import urllib.request
from pathlib import Path

OSV = "https://api.osv.dev/v1/querybatch"
# The local project has no upstream release; querying it is meaningless.
_SELF = "antiek"
# uv.lock on main carries ~194 packages. A parse far below that means the file
# moved, the format changed, or the read failed — and an empty query would
# return "no vulnerabilities", which is the failure this floor exists to stop.
_MIN_PINS = 100


def pins(lock: Path) -> list[tuple[str, str]]:
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return [
        (p["name"], p["version"])
        for p in data.get("package", [])
        if p.get("name") and p.get("version") and p["name"] != _SELF
    ]


def main() -> int:
    lock = Path(sys.argv[1] if len(sys.argv) > 1 else "uv.lock")
    if not lock.exists():
        print(f"::error::{lock} not found")
        return 1
    found = pins(lock)
    print(f"parsed {len(found)} pinned packages from {lock}")
    if len(found) < _MIN_PINS:
        print(
            f"::error title=Partial parse::only {len(found)} pins parsed "
            f"(expected >= {_MIN_PINS}); refusing to report a clean audit over nothing"
        )
        return 1

    body = json.dumps(
        {"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in found]}
    ).encode()
    req = urllib.request.Request(OSV, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        results = json.loads(resp.read()).get("results", [])

    if len(results) != len(found):
        print(f"::error::OSV returned {len(results)} results for {len(found)} queries")
        return 1

    hits = [
        (n, v, [x["id"] for x in (r.get("vulns") or [])])
        for (n, v), r in zip(found, results)
        if r.get("vulns")
    ]
    if not hits:
        print(f"uv.lock: no known vulnerabilities across {len(found)} packages")
        return 0

    total = sum(len(ids) for _, _, ids in hits)
    print(f"::error title=uv.lock vulnerabilities::{total} advisories in {len(hits)} packages")
    for name, version, ids in sorted(hits):
        print(f"  {name}=={version}  {', '.join(ids)}")
    print("Fix with: uv lock --upgrade-package <name>  (do NOT hand-edit; hashes and the dep graph would break)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
