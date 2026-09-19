"""Redacted, bounded operator migration for globally keyed investigation streams."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import stat
from collections import Counter
from pathlib import Path

from substrate.investigation_stream_migration import (
    MigrationLimits,
    migrate_legacy_to_composite,
    resume_composite_to_legacy,
    resume_legacy_to_composite,
    rollback_composite_to_legacy,
)
from substrate.investigation_streams import list_composite_investigation_ids
from substrate.investigation_tenancy import (
    InvestigationAuthority,
    InvestigationOwnershipConflict,
    bind_historic_operator_stream_lease,
    default_tenancy_root,
    legacy_lease_storage_state,
)
from substrate.multi_user.auth import operator_claims

_MAX_CLASSIFICATION_LINE_BYTES = 256 * 1024
_MAX_CLASSIFICATION_STREAM_BYTES = 64 * 1024 * 1024


def _jsonl_stream_kind(path: Path) -> str:
    """Classify only the explicit owner-scoped artifact event envelope.

    Unknown, malformed, empty, or oversized streams remain investigation
    candidates so migration never silently drops ambiguous historic data.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return "unknown"
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return "unknown"
        raw = bytearray()
        while chunk := os.read(fd, 64 * 1024):
            raw.extend(chunk)
            if len(raw) > _MAX_CLASSIFICATION_STREAM_BYTES:
                return "unknown"
        if raw and not raw.endswith(b"\n"):
            return "unknown"
        rows = 0
        for line in raw.splitlines():
            if len(line) > _MAX_CLASSIFICATION_LINE_BYTES:
                return "unknown"
            try:
                row = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return "unknown"
            payload = row.get("payload") if isinstance(row, dict) else None
            intent = payload.get("intent") if isinstance(payload, dict) else None
            if (
                row.get("investigation_id") != path.stem
                or not isinstance(intent, str)
                or not intent.startswith("research_artifact_v1:")
            ):
                return "unknown"
            rows += 1
    finally:
        os.close(fd)
    return "owner_scoped_artifact_event" if rows else "unknown"


def _census_digest_key(root: Path) -> bytes:
    """Read an existing tenancy key without making dry-run mutate the root."""
    configured = os.environ.get("ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET", "")
    if configured:
        return hashlib.sha256(configured.encode()).digest()
    path = root / ".tenancy" / "authority-key-v1"
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return os.urandom(32)
    except OSError as exc:
        raise RuntimeError("investigation census key is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != 32:
            raise RuntimeError("investigation census key is unsafe")
        key = os.read(fd, 33)
        if len(key) != 32:
            raise RuntimeError("investigation census key is unsafe")
        return key
    finally:
        os.close(fd)


def _candidates(
    root: Path, *, max_entries: int = 100_000
) -> list[tuple[str, str, str]]:
    if max_entries <= 0:
        raise ValueError("census entry limit must be positive")
    digest_key = _census_digest_key(root)
    by_id: dict[str, set[str]] = {}
    matched_entries = 0
    try:
        entries = os.scandir(root)
    except OSError:
        raise RuntimeError("investigation census root is unreadable") from None
    with entries:
        try:
            for entry in entries:
                suffix = Path(entry.name).suffix
                if suffix not in {".jsonl", ".parquet"}:
                    continue
                matched_entries += 1
                if matched_entries > max_entries:
                    raise ValueError("investigation census exceeds entry limit")
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    state = "quarantine_unreadable"
                else:
                    state = (
                        "valid_regular"
                        if stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                        else "quarantine_nonregular"
                    )
                path = root / entry.name
                if suffix == ".jsonl" and state == "valid_regular":
                    kind = _jsonl_stream_kind(path)
                    if kind == "owner_scoped_artifact_event":
                        state = kind
                by_id.setdefault(entry.name[: -len(suffix)], set()).add(state)
        except OSError:
            raise RuntimeError("investigation census failed during enumeration") from None
    result = []
    for investigation_id, states in by_id.items():
        digest = hmac.new(
            digest_key,
            b"antiek-w3d-census\x00" + investigation_id.encode(),
            hashlib.sha256,
        ).hexdigest()
        if states == {"owner_scoped_artifact_event"}:
            state = "excluded_owner_scoped_artifact_event"
        elif states == {"valid_regular"}:
            state = "valid_regular"
        else:
            state = "quarantine_nonregular"
        result.append((digest, investigation_id, state))
    return sorted(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bind historic investigation streams to operator")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--copy-composite", action="store_true")
    action.add_argument("--resume-composite", action="store_true")
    action.add_argument("--rollback-composite", action="store_true")
    action.add_argument("--resume-rollback", action="store_true")
    action.add_argument("--verify-composite", action="store_true")
    parser.add_argument("--approve-operator-migration", action="store_true")
    parser.add_argument("--approve-composite-migration", action="store_true")
    parser.add_argument("--approve-composite-rollback", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--resume-after", metavar="SOURCE_DIGEST")
    parser.add_argument("--include-entries", action="store_true")
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--max-file-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=1024 * 1024 * 1024)
    parser.add_argument("--max-census-entries", type=int, default=100_000)
    args = parser.parse_args(argv)
    root = (args.root or default_tenancy_root()).expanduser().resolve()
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    if not 1 <= args.max_census_entries <= 10_000_000:
        parser.error("--max-census-entries must be between 1 and 10000000")
    composite_action = any(
        (
            args.copy_composite,
            args.resume_composite,
            args.rollback_composite,
            args.resume_rollback,
            args.verify_composite,
        )
    )
    if args.apply and composite_action:
        parser.error("--apply cannot be combined with a composite action")
    all_candidates = _candidates(root, max_entries=args.max_census_entries)
    summary = Counter(state for _digest, _investigation_id, state in all_candidates)
    migration_candidates = [
        row for row in all_candidates if row[2] != "excluded_owner_scoped_artifact_event"
    ]
    candidates = migration_candidates
    action_authorities: dict[str, InvestigationAuthority] = {}
    if composite_action and not args.copy_composite:
        operator_id = operator_claims().user_id
        existing_ids = {investigation_id for _, investigation_id, _ in candidates}
        for source_digest, investigation_id, _state in candidates:
            action_authorities[source_digest] = InvestigationAuthority(
                operator_id,
                investigation_id,
                root=root,
            )
        digest_key = _census_digest_key(root)
        for investigation_id in list_composite_investigation_ids(
            operator_id,
            root=root,
        ):
            if investigation_id in existing_ids:
                continue
            authority = InvestigationAuthority(operator_id, investigation_id, root=root)
            source_digest = hmac.new(
                digest_key,
                b"antiek-w3d-composite\x00" + bytes.fromhex(authority.stream_key),
                hashlib.sha256,
            ).hexdigest()
            candidates.append((source_digest, investigation_id, "valid_regular"))
            action_authorities[source_digest] = authority
        candidates.sort()
    if args.resume_after:
        candidates = [row for row in candidates if row[0] > args.resume_after]
    candidates = candidates[: args.batch_size]
    if not args.apply and not composite_action:
        receipt: dict[str, object] = {
            "total_discovered": len(all_candidates),
            "migration_denominator": len(migration_candidates),
            "batch_count": len(candidates),
            "summary": dict(sorted(summary.items())),
            "resume_after": candidates[-1][0] if candidates else args.resume_after,
        }
        if args.include_entries:
            receipt["entries"] = [
                {"source_digest": digest, "disposition": state}
                for digest, _investigation_id, state in candidates
            ]
        print(json.dumps(receipt, sort_keys=True))
        return 0
    try:
        limits = MigrationLimits(
            max_rows=args.max_rows,
            max_file_bytes=args.max_file_bytes,
            max_total_bytes=args.max_total_bytes,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if composite_action:
        if args.rollback_composite or args.resume_rollback:
            if not args.approve_composite_rollback:
                parser.error(
                    "rollback requires --approve-composite-rollback"
                )
        elif not args.approve_composite_migration:
            parser.error(
                "composite migration requires --approve-composite-migration"
            )
        completed: list[dict[str, object]] = []
        quarantined: list[dict[str, str]] = []
        for source_digest, investigation_id, state in candidates:
            if state != "valid_regular":
                quarantined.append(
                    {"source_digest": source_digest, "reason_code": state}
                )
                continue
            authority = action_authorities.get(
                source_digest,
                InvestigationAuthority(
                    operator_claims().user_id,
                    investigation_id,
                    root=root,
                ),
            )
            try:
                if args.copy_composite:
                    bind_historic_operator_stream_lease(authority)
                    result = migrate_legacy_to_composite(authority, limits=limits)
                elif args.resume_composite:
                    result = resume_legacy_to_composite(authority, limits=limits)
                elif args.rollback_composite:
                    result = rollback_composite_to_legacy(authority, limits=limits)
                elif args.resume_rollback:
                    result = resume_composite_to_legacy(authority, limits=limits)
                else:
                    if legacy_lease_storage_state(authority) != "composite":
                        raise InvestigationOwnershipConflict(
                            "verification requires composite authority"
                        )
                    result = resume_legacy_to_composite(authority, limits=limits)
            except (ValueError, InvestigationOwnershipConflict):
                quarantined.append(
                    {
                        "source_digest": source_digest,
                        "reason_code": "validation_failed",
                    }
                )
                continue
            completed.append(result.as_dict())
        print(
            json.dumps(
                {
                    "attempted": len(candidates),
                    "completed": completed,
                    "quarantined": quarantined,
                    "resume_after": (
                        candidates[-1][0] if candidates else args.resume_after
                    ),
                },
                sort_keys=True,
            )
        )
        return 1 if quarantined else 0
    if not args.approve_operator_migration:
        parser.error("--apply requires --approve-operator-migration")
    migrated: list[str] = []
    quarantined: list[str] = []
    for source_digest, investigation_id, state in candidates:
        if state != "valid_regular":
            quarantined.append(source_digest)
            continue
        authority = InvestigationAuthority(
            operator_claims().user_id, investigation_id, root=root
        )
        bind_historic_operator_stream_lease(authority)
        migrated.append(source_digest)
    print(
        json.dumps(
            {
                "attempted": len(candidates),
                "migrated": migrated,
                "quarantined": quarantined,
                "resume_after": candidates[-1][0] if candidates else args.resume_after,
            },
            sort_keys=True,
        )
    )
    return 1 if quarantined else 0


if __name__ == "__main__":
    raise SystemExit(main())
