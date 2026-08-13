"""Offline statement verifier for AFA-S6 (stdlib only).

An external auditor runs this WITHOUT the rest of the repo::

    python -m substrate.ad_inventory.verify_statement \\
        statement.json proof.json root.txt

Exit 0 + prints ``VALID`` on success; exit 1 + ``INVALID: <reason>`` on
failure. Imports are grepped in tests to prove isolation: only the Python
standard library (json, hashlib, sys, pathlib, argparse, typing).

Leaf contract (merkle-leaf-v1) — frozen here so the file is self-contained:

    leaf_hash(payload) = sha256(b"\\x00" + payload)
    node_hash(L, R)    = sha256(b"\\x01" + L + R)
    payload            = canonical JSON of the statement
                         (sort_keys=True, separators=(",", ":"), UTF-8)

Odd-level unpaired nodes promote unchanged (no self-hash).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"
MERKLE_SERIALIZATION_VERSION = "merkle-leaf-v1"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _leaf_hash(payload: bytes) -> bytes:
    return hashlib.sha256(_LEAF_PREFIX + payload).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


def verify(
    statement: dict[str, Any],
    proof: dict[str, Any],
    root_hex: str,
) -> tuple[bool, str]:
    """Return (ok, reason). reason is 'ok' on success."""
    if not isinstance(statement, dict):
        return False, "statement is not a JSON object"
    if "payee_id" not in statement or "total_cents" not in statement:
        return False, "statement missing required fields (payee_id, total_cents)"
    if "period" not in statement:
        return False, "statement missing period"

    # Accept bare proof or envelope {"proof": {...}, "month_root_hex": ...}.
    root_from_proof = None
    if "proof" in proof and isinstance(proof["proof"], dict):
        root_from_proof = proof.get("month_root_hex")
        inner = proof["proof"]
    else:
        inner = proof

    siblings = inner.get("siblings")
    directions = inner.get("directions")
    if not isinstance(siblings, list) or not isinstance(directions, list):
        return False, "proof missing siblings/directions lists"
    if len(siblings) != len(directions):
        return False, "proof siblings/directions length mismatch"

    if root_from_proof and root_from_proof.lower() != root_hex.lower():
        return False, (
            f"proof envelope root {root_from_proof} != provided root {root_hex}"
        )

    payload = _canonical_json(statement).encode("utf-8")
    running = _leaf_hash(payload)
    for sib_hex, direction in zip(siblings, directions, strict=True):
        if not isinstance(sib_hex, str) or not isinstance(direction, str):
            return False, "proof entry type error"
        try:
            sib = bytes.fromhex(sib_hex)
        except ValueError:
            return False, f"sibling not hex: {sib_hex!r}"
        if len(sib) != 32:
            return False, f"sibling not 32 bytes: {sib_hex!r}"
        if direction == "R":
            running = _node_hash(running, sib)
        elif direction == "L":
            running = _node_hash(sib, running)
        else:
            return False, f"bad direction {direction!r} (want L or R)"

    if running.hex() != root_hex.lower().strip():
        return False, (
            f"recomputed root {running.hex()} != published root {root_hex.lower().strip()}"
        )
    return True, "ok"


def _load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _load_root(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().splitlines()[0].strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m substrate.ad_inventory.verify_statement",
        description=(
            "Offline AFA-S6 statement verifier (stdlib only). "
            "Validates a payee statement's inclusion proof against a "
            "published month root."
        ),
    )
    p.add_argument("statement", type=Path, help="path to statement JSON")
    p.add_argument("proof", type=Path, help="path to proof JSON (bare or envelope)")
    p.add_argument("root", type=Path, help="path to root.txt (hex digest)")
    args = p.parse_args(argv)

    try:
        statement = _load_json(args.statement)
        proof = _load_json(args.proof)
        root_hex = _load_root(args.root)
    except (OSError, json.JSONDecodeError, IndexError) as e:
        print(f"INVALID: failed to load inputs: {e}", file=sys.stderr)
        return 1

    ok, reason = verify(statement, proof, root_hex)
    if ok:
        payee = statement.get("payee_id", "?")
        period = statement.get("period", "?")
        cents = statement.get("total_cents", "?")
        print(f"VALID payee={payee} period={period} total_cents={cents} root={root_hex[:16]}…")
        return 0
    print(f"INVALID: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
