"""Fail closed unless the durable event-consumer schema contract is exact."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# ``python tools/this_file.py`` otherwise puts only ``tools/`` first and may
# resolve an unrelated editable Antiek checkout on operator machines.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.schema import (  # noqa: E402
    _V19_EVENT_REQUIRED_SHAPE,
    _V19_FRONTIER_REQUIRED_SHAPE,
    _V19_RECEIPT_REQUIRED_SHAPE,
    _v19_event_shape_is_valid,
    _v19_frontier_shape_is_valid,
    _v19_receipt_shape_is_valid,
)

SUPPORTED_ACTIONS = {"note.emerged", "question.identified", "marginalia.noted"}


def verify(db_path: str) -> None:
    mismatches: list[str] = []
    with connect_write(db_path, purpose="deploy/event_consumer_schema_verify", timeout_s=30) as con:
        event_shape = {
            row[0]: (row[1], row[2], row[3])
            for row in con.execute("DESCRIBE event_consumer_events").fetchall()
        }
        receipt_shape = {
            row[0]: (row[1], row[2], row[3])
            for row in con.execute("DESCRIBE event_consumer_receipts").fetchall()
        }
        frontier_shape = {
            row[0]: (row[1], row[2], row[3])
            for row in con.execute("DESCRIBE event_consumer_frontiers").fetchall()
        }
        event_valid = _v19_event_shape_is_valid(con)
        receipt_valid = _v19_receipt_shape_is_valid(con)
        frontier_valid = _v19_frontier_shape_is_valid(con)
        if event_shape != _V19_EVENT_REQUIRED_SHAPE or not event_valid:
            mismatches.append("event_consumer_events columns/constraints/indexes")
        if receipt_shape != _V19_RECEIPT_REQUIRED_SHAPE or not receipt_valid:
            mismatches.append("event_consumer_receipts columns/constraints/index")
        if frontier_shape != _V19_FRONTIER_REQUIRED_SHAPE or not frontier_valid:
            mismatches.append("event_consumer_frontiers columns/constraints")
        if not mismatches:
            events = con.execute(
                "SELECT consumer_name, consumer_version, investigation_id, "
                "logical_ordinal, event_id, action_type, normalized_sha256, "
                "resolution, chain_sha256, created_at, resolved_at "
                "FROM event_consumer_events ORDER BY "
                "consumer_name, consumer_version, investigation_id, logical_ordinal"
            ).fetchall()
            expected_frontiers: dict[tuple[str, int, str], tuple[int, str]] = {}
            expected_receipts: dict[
                tuple[str, int, str], tuple[str, str, str, str]
            ] = {}
            for row in events:
                consumer, version, investigation, ordinal = row[:4]
                (
                    event_id,
                    action_type,
                    normalized_sha256,
                    resolution,
                    chain,
                    created_at,
                    resolved_at,
                ) = row[4:]
                key = (consumer, version, investigation)
                prior_ordinal, prior_chain = expected_frontiers.get(key, (0, ""))
                if ordinal != prior_ordinal:
                    mismatches.append(f"ordinal gap for {key!r} at {ordinal}")
                    continue
                expected_chain = hashlib.sha256(
                    "\0".join(
                        [prior_chain, str(ordinal), event_id, normalized_sha256]
                    ).encode()
                ).hexdigest()
                if chain != expected_chain:
                    mismatches.append(f"chain mismatch for event {event_id}")
                if (action_type in SUPPORTED_ACTIONS) != (
                    resolution in ("succeeded", "quarantined")
                ):
                    mismatches.append(f"action/resolution mismatch for event {event_id}")
                if resolved_at < created_at:
                    mismatches.append(f"timestamp order mismatch for event {event_id}")
                expected_frontiers[key] = (ordinal + 1, expected_chain)
                if resolution in ("succeeded", "quarantined"):
                    expected_receipts[(consumer, version, event_id)] = (
                        investigation,
                        action_type,
                        normalized_sha256,
                        resolution,
                    )

            frontiers = con.execute(
                "SELECT consumer_name, consumer_version, investigation_id, "
                "next_ordinal, chain_sha256 FROM event_consumer_frontiers"
            ).fetchall()
            actual_frontiers = {
                row[:3]: (row[3], row[4] or "") for row in frontiers
            }
            for key in set(expected_frontiers) | set(actual_frontiers):
                if actual_frontiers.get(key, (0, "")) != expected_frontiers.get(
                    key, (0, "")
                ):
                    mismatches.append(f"frontier mismatch for {key!r}")

            receipts = con.execute(
                "SELECT consumer_name, consumer_version, event_id, investigation_id, "
                "action_type, normalized_sha256, status FROM event_consumer_receipts"
            ).fetchall()
            actual_receipts = {
                row[:3]: (row[3], row[4], row[5], row[6]) for row in receipts
            }
            for key in set(expected_receipts) | set(actual_receipts):
                if actual_receipts.get(key) != expected_receipts.get(key):
                    mismatches.append(f"receipt/ledger mismatch for {key!r}")
    if mismatches:
        raise RuntimeError("event consumer schema contract mismatch: " + ", ".join(mismatches))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    args = parser.parse_args()
    verify(args.db_path)
    print("event consumer schema contract verified")


if __name__ == "__main__":
    main()
