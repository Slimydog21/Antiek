"""Stdlib Merkle tree for AFA-S6 month roots (hashlib only).

Leaf and node domain separation follows the certificate-transparency
style prefixes so a leaf hash can never collide with an interior node
hash of the same payload bytes:

    leaf_hash(bytes) = sha256(b"\\x00" + bytes)
    node_hash(L, R)  = sha256(b"\\x01" + L + R)

Odd levels promote the unpaired node unchanged (no self-hash, no
duplicate-last). Single-leaf trees have root == that leaf hash.

Serialization version ``merkle-leaf-v1`` is stamped on every root
record: a proof is only as durable as its leaf contract is frozen.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

# Domain-separation prefixes (frozen for merkle-leaf-v1).
_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"

# Bump when leaf domain, node domain, or odd-level rule changes.
MERKLE_SERIALIZATION_VERSION: str = "merkle-leaf-v1"


def sha256_hex(data: bytes) -> str:
    """Lowercase hex digest of sha256(data)."""
    return hashlib.sha256(data).hexdigest()


def leaf_hash(payload: bytes) -> bytes:
    """Hash a leaf payload with the leaf domain prefix. Returns raw 32 bytes."""
    return hashlib.sha256(_LEAF_PREFIX + payload).digest()


def leaf_hash_hex(payload: bytes) -> str:
    """Hex form of :func:`leaf_hash`."""
    return leaf_hash(payload).hex()


def node_hash(left: bytes, right: bytes) -> bytes:
    """Hash an interior node (left || right) with the node domain prefix."""
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


@dataclass(frozen=True)
class InclusionProof:
    """Sibling path from a leaf to the root.

    ``siblings`` is ordered rootward: index 0 is the sibling of the leaf,
    index -1 is the sibling just under the root. ``directions`` is parallel
    and records whether the sibling sits on the left (``"L"``) or right
    (``"R"``) of the running hash — required because node_hash is ordered.
    """

    leaf_index: int
    siblings: tuple[str, ...]  # hex digests
    directions: tuple[str, ...]  # "L" | "R" per sibling

    def to_dict(self) -> dict[str, object]:
        return {
            "leaf_index": self.leaf_index,
            "siblings": list(self.siblings),
            "directions": list(self.directions),
            "serialization_version": MERKLE_SERIALIZATION_VERSION,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> InclusionProof:
        """Fail-closed proof parse: a malformed proof must never coerce."""
        raw_index = d.get("leaf_index")
        raw_siblings = d.get("siblings")
        raw_directions = d.get("directions")
        if not isinstance(raw_index, int):
            raise ValueError("proof leaf_index must be an int")
        if not isinstance(raw_siblings, list) or not isinstance(raw_directions, list):
            raise ValueError("proof siblings/directions must be lists")
        return cls(
            leaf_index=raw_index,
            siblings=tuple(str(s) for s in raw_siblings),
            directions=tuple(str(x) for x in raw_directions),
        )


@dataclass(frozen=True)
class MerkleTree:
    """Binary Merkle tree over an ordered sequence of leaf payloads.

    Construction is pure and clock-free. Leaves are hashed in the order
    given — the caller is responsible for a stable sort (month close sorts
    statements by payee_id).
    """

    leaf_payloads: tuple[bytes, ...]
    leaf_hashes: tuple[bytes, ...]
    root: bytes
    # levels[0] = leaf hashes; levels[-1] = [root]
    levels: tuple[tuple[bytes, ...], ...]

    @property
    def root_hex(self) -> str:
        return self.root.hex()

    @property
    def size(self) -> int:
        return len(self.leaf_hashes)


def build_tree(leaf_payloads: Sequence[bytes]) -> MerkleTree:
    """Build a Merkle tree over ``leaf_payloads`` (order preserved).

    Empty input is rejected — a month with zero statements has no root
    (the close job surfaces that as a distinct empty-month outcome rather
    than inventing a null hash).
    """
    if not leaf_payloads:
        raise ValueError("cannot build Merkle tree over zero leaves")

    leaves = tuple(leaf_hash(p) for p in leaf_payloads)
    levels: list[tuple[bytes, ...]] = [leaves]
    current = leaves
    while len(current) > 1:
        nxt: list[bytes] = []
        i = 0
        while i < len(current):
            if i + 1 < len(current):
                nxt.append(node_hash(current[i], current[i + 1]))
                i += 2
            else:
                # Odd count: promote the unpaired node unchanged.
                nxt.append(current[i])
                i += 1
        current = tuple(nxt)
        levels.append(current)
    return MerkleTree(
        leaf_payloads=tuple(leaf_payloads),
        leaf_hashes=leaves,
        root=current[0],
        levels=tuple(levels),
    )


def prove(tree: MerkleTree, leaf_index: int) -> InclusionProof:
    """Generate an inclusion proof for ``leaf_index`` (0-based)."""
    if leaf_index < 0 or leaf_index >= tree.size:
        raise IndexError(f"leaf_index {leaf_index} out of range [0, {tree.size})")
    siblings: list[str] = []
    directions: list[str] = []
    idx = leaf_index
    for level in tree.levels[:-1]:
        if len(level) == 1:
            break
        if idx % 2 == 0:
            # Even: sibling is to the right, if present.
            if idx + 1 < len(level):
                siblings.append(level[idx + 1].hex())
                directions.append("R")
            # else: unpaired promote — no sibling at this level
        else:
            # Odd: sibling is to the left.
            siblings.append(level[idx - 1].hex())
            directions.append("L")
        idx //= 2
        # When an odd-length level promoted the last node, the next-level
        # index for a promoted last element is len//2 (integer division of
        # the last index). For paired nodes idx//2 is correct. For a
        # promoted unpaired at index 2k (even last), idx//2 = k which is
        # also the slot it occupies after promote. Good.
        # But wait: when we skip adding a sibling for unpaired, we still
        # need idx to map to the promoted slot. Unpaired only happens at
        # the last index when len is odd: last_idx = len-1 (even, since
        # len odd ⇒ len-1 even). idx//2 works.
    return InclusionProof(
        leaf_index=leaf_index,
        siblings=tuple(siblings),
        directions=tuple(directions),
    )


def verify_inclusion(
    leaf_payload: bytes,
    proof: InclusionProof,
    root_hex: str,
) -> bool:
    """Recompute the path from ``leaf_payload`` + ``proof`` and compare to root.

    Pure: no tree, no DB. Returns True iff the proof authenticates the leaf
    against the published root under merkle-leaf-v1 rules.
    """
    running = leaf_hash(leaf_payload)
    if len(proof.siblings) != len(proof.directions):
        return False
    for sib_hex, direction in zip(proof.siblings, proof.directions, strict=True):
        try:
            sib = bytes.fromhex(sib_hex)
        except ValueError:
            return False
        if len(sib) != 32:
            return False
        if direction == "R":
            running = node_hash(running, sib)
        elif direction == "L":
            running = node_hash(sib, running)
        else:
            return False
    return running.hex() == root_hex.lower()


__all__ = [
    "MERKLE_SERIALIZATION_VERSION",
    "InclusionProof",
    "MerkleTree",
    "build_tree",
    "leaf_hash",
    "leaf_hash_hex",
    "node_hash",
    "prove",
    "sha256_hex",
    "verify_inclusion",
]
