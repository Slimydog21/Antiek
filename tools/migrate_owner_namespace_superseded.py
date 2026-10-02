# SUPERSEDED — DO NOT RUN. Use ``tools/migrate_owner_namespace.py`` instead.
#
# This 71-line draft only understands a list-shaped or ``{models|rows: [...]}``
# JSON file, but the real user-model registry on disk is ``{record_id:
# record}`` — against a real registry it reports ``rows_to_reown=0`` and exits
# 0 on ``--apply`` while changing nothing (a silent no-op, proven in the
# #3197-vs-#3382 comparative review against a live fixture). It also never
# re-sealed BYOK credentials (bound to owner+handle) and ignored the other
# five owner-keyed stores. ``main()`` below now refuses to run; the functions
# remain only so the file's history stays readable.
"""One-way migration: re-own legacy `__operator__` rows to the derived owner.

Namespace Option A (DECISION-REQUIRED-owner-namespace.md). Explicit and
auditable. Refuses to run against a registry that contains rows for more
than one legacy owner. Never implements an implicit read-fallback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_LEGACY = "__operator__"


def migrate_registry(registry_path: Path, email: str, *, apply: bool) -> int:
    from interfaces.research.api.account_memory_identity import (
        derive_owner_from_verified_email,
    )

    derived = derive_owner_from_verified_email(email)
    if not derived:
        print(f"ERROR: cannot derive owner from {email!r}", file=sys.stderr)
        return 2

    data = json.loads(registry_path.read_text())
    rows = data if isinstance(data, list) else data.get("models") or data.get("rows") or []
    if not isinstance(rows, list):
        print("ERROR: registry shape is not a list or {models|rows: list}", file=sys.stderr)
        return 2

    owners = {str(r.get("owner_user_id", "")) for r in rows if isinstance(r, dict)}
    non_empty = {o for o in owners if o}
    if len(non_empty) > 1:
        print(
            f"ERROR: refusing — registry has {len(non_empty)} distinct owners "
            f"{sorted(non_empty)[:5]}; this migration only re-owns {_LEGACY!r}",
            file=sys.stderr,
        )
        return 3

    changed = 0
    for r in rows:
        if isinstance(r, dict) and r.get("owner_user_id") == _LEGACY:
            r["owner_user_id"] = derived
            r["migrated_from_owner"] = _LEGACY
            r["migrated_to_email"] = email.strip().casefold()
            changed += 1

    print(f"email={email!r} derived={derived} rows_to_reown={changed} apply={apply}")
    if apply and changed:
        registry_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"wrote {registry_path}")
    elif not apply:
        print("dry-run; pass --apply to write")
    return 0


def main(argv: list[str] | None = None) -> int:
    print(
        "ERROR: this tool is superseded and unsafe (silent 0-row no-op on the "
        "real registry shape). Use tools/migrate_owner_namespace.py instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
