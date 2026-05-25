#!/usr/bin/env python3
"""Substrate/dispatch boundary lint — forbid direct vendor-SDK imports outside
``substrate/dispatch/providers/``.

The invariant (CLAUDE.md §16 + docs/decisions/substrate_dispatch_boundary.md):
the substrate is **vendor-agnostic**. Concrete vendor SDKs — openai, anthropic,
daytona, browserbase, modal, … — may be imported ONLY inside the adapter layer
``substrate/dispatch/providers/``. Everywhere else in ``substrate/`` must go
through the dispatch router's vendor-neutral interface. This keeps the
dispatch posture swappable (Hermes-primary; §16) and the single-writer /
provenance core free of vendor coupling.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.

NOTE (provenance): the CI step that runs this (`.github/workflows/ci.yml` →
"Substrate/dispatch boundary check") was introduced by the DDIA-execution SPR-03
work, but the script itself was never landed in the product tree. This is that
script — implemented to the stated invariant and verified to pass on the
consolidated tree (no vendor imports in substrate/ outside providers/).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_SUBSTRATE = _REPO / "substrate"
_ALLOWED_DIR = _SUBSTRATE / "dispatch" / "providers"

# Concrete vendor SDKs the dispatch layer adapts. Importing any of these outside
# the providers/ adapter couples the substrate to a specific vendor. Match is by
# exact module or dotted-prefix, so "google.generativeai" does NOT flag the
# unrelated "google.protobuf".
_VENDOR_SDKS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "daytona",
    "daytona_sdk",
    "browserbase",
    "modal",
    "cohere",
    "mistralai",
    "together",
    "groq",
    "replicate",
    "google.generativeai",
    "vertexai",
    "boto3",
    "pulumi",
)


def _is_vendor(module: str | None) -> bool:
    if not module:
        return False
    return any(module == v or module.startswith(v + ".") for v in _VENDOR_SDKS)


def find_violations() -> list[str]:
    """Return ``path:line: message`` strings for every vendor-SDK import in
    ``substrate/`` outside ``substrate/dispatch/providers/``."""
    out: list[str] = []
    for py in sorted(_SUBSTRATE.rglob("*.py")):
        if _ALLOWED_DIR in py.parents:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        rel = py.relative_to(_REPO)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_vendor(alias.name):
                        out.append(
                            f"{rel}:{node.lineno}: imports vendor SDK "
                            f"'{alias.name}' outside dispatch/providers/"
                        )
            elif isinstance(node, ast.ImportFrom):
                if _is_vendor(node.module):
                    out.append(
                        f"{rel}:{node.lineno}: imports from vendor SDK "
                        f"'{node.module}' outside dispatch/providers/"
                    )
    return out


def main() -> int:
    violations = find_violations()
    if violations:
        print("Substrate/dispatch boundary violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nVendor SDKs may be imported ONLY inside "
            "substrate/dispatch/providers/. Route everything else through the "
            "dispatch router's vendor-neutral interface "
            "(docs/decisions/substrate_dispatch_boundary.md)."
        )
        return 1
    print("OK: no vendor-SDK imports in substrate/ outside dispatch/providers/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
