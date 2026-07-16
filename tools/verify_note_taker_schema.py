"""Fail closed unless durable note-taker state is structurally coherent."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from roles.note_taker.parser import parse_notes_response  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.schema import (  # noqa: E402
    _v20_configuration_shape_is_valid,
    _v20_note_taker_shape_is_valid,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify(db_path: str) -> None:
    mismatches: list[str] = []
    with connect_write(
        db_path, purpose="deploy/note_taker_schema_verify", timeout_s=30
    ) as con:
        if not _v20_configuration_shape_is_valid(con):
            mismatches.append("note_taker_configurations shape")
        if not _v20_note_taker_shape_is_valid(con):
            mismatches.append("note_taker_windows shape")
        if mismatches:
            raise RuntimeError(
                "note-taker schema contract mismatch: " + ", ".join(mismatches)
            )

        configurations = {
            (version, investigation): (threshold, prompt_sha, configuration_sha)
            for version, investigation, threshold, prompt_sha, configuration_sha in con.execute(
                "SELECT consumer_version, investigation_id, threshold, "
                "prompt_sha256, configuration_sha256 FROM note_taker_configurations"
            ).fetchall()
        }
        for (version, investigation), (
            threshold,
            prompt_sha,
            configuration_sha,
        ) in configurations.items():
            expected = _digest(
                _canonical(
                    {
                        "consumer": "note-taker",
                        "consumer_version": version,
                        "threshold": threshold,
                        "prompt_sha256": prompt_sha,
                    }
                )
            )
            if configuration_sha != expected:
                mismatches.append(f"configuration digest for {investigation}")

        expected_ordinal: dict[tuple[int, str], int] = {}
        windows = con.execute(
            "SELECT window_id, consumer_version, investigation_id, threshold, "
            "ordinal, first_event_id, last_event_id, source_event_ids_json, "
            "source_digest, request_json, request_sha256, "
            "provider_idempotency_key, state, raw_result, raw_result_sha256 "
            "FROM note_taker_windows ORDER BY consumer_version, "
            "investigation_id, ordinal"
        ).fetchall()
        for row in windows:
            (
                window_id,
                version,
                investigation,
                threshold,
                ordinal,
                first_event_id,
                last_event_id,
                source_json,
                source_digest,
                request_json,
                request_sha,
                provider_key,
                state,
                raw_result,
                raw_result_sha,
            ) = row
            key = (version, investigation)
            if configurations.get(key, (None, None, None))[0] != threshold:
                mismatches.append(f"window/configuration mismatch for {window_id}")
            if ordinal != expected_ordinal.get(key, 0):
                mismatches.append(f"window ordinal gap for {window_id}")
            expected_ordinal[key] = ordinal + 1
            try:
                source_ids = json.loads(source_json)
                request = json.loads(request_json)
            except (TypeError, json.JSONDecodeError):
                mismatches.append(f"invalid canonical JSON for {window_id}")
                continue
            if (
                not isinstance(source_ids, list)
                or len(source_ids) != threshold
                or not all(isinstance(value, str) and value for value in source_ids)
                or source_ids[0] != first_event_id
                or source_ids[-1] != last_event_id
            ):
                mismatches.append(f"source manifest for {window_id}")
                continue
            identity = _canonical(
                {
                    "consumer": "note-taker",
                    "consumer_version": version,
                    "investigation_id": investigation,
                    "threshold": threshold,
                    "source_event_ids": source_ids,
                }
            )
            if window_id != _digest(identity) or provider_key != window_id:
                mismatches.append(f"window identity for {window_id}")
            if source_digest != _digest(source_json):
                mismatches.append(f"source digest for {window_id}")
            if request_sha != _digest(request_json):
                mismatches.append(f"request digest for {window_id}")
            if not isinstance(request, dict) or (
                request.get("investigation_id") != investigation
                or request.get("source_event_ids") != source_ids
            ):
                mismatches.append(f"request identity for {window_id}")
            if raw_result is not None and raw_result_sha != _digest(raw_result):
                mismatches.append(f"provider result digest for {window_id}")
            outbox = con.execute(
                "SELECT state FROM write_event_outbox WHERE "
                "aggregate_kind='note_taker_window' AND aggregate_id=?",
                [window_id],
            ).fetchall()
            if state in {"materialized", "completed"}:
                expected_events = (
                    len(parse_notes_response(raw_result, canonical_event_ids=source_ids))
                    if isinstance(raw_result, str)
                    else -1
                )
                if len(outbox) != expected_events:
                    mismatches.append(f"materialized event count for {window_id}")
            if state == "completed" and any(item[0] != "delivered" for item in outbox):
                mismatches.append(f"pending completed events for {window_id}")

    if mismatches:
        raise RuntimeError(
            "note-taker schema contract mismatch: " + ", ".join(mismatches)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    args = parser.parse_args()
    verify(args.db_path)
    print("note-taker schema contract verified")


if __name__ == "__main__":
    main()
