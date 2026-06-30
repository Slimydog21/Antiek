"""ASR SR-06 operator tool: backfill legacy NULL ``documents.content_class``.

Forward ingest now stamps every rights-relevant row with an explicit
``content_class``. The remaining ``NULL`` values are legacy rows, and SR-07's
fail-closed retrieval flip is blocked until an operator can inspect and backfill
them. This tool is that offline step.

Rules are intentionally conservative:

* third-party personal-ingest document types -> ``personal_reading``
* stored ``metadata.license_content_class`` -> that explicit class
* arXiv rows with ``rights_tier`` T2/T3 -> the gated floor
* ``book_assets.license_basis`` with CC0/CC-BY markers -> the corrected open class
* everything else -> unresolved

Dry-run is the default. ``--apply`` refuses unresolved rows unless the operator
also passes ``--allow-unresolved-to-gated``, which moves those rows to
``restricted_pending_opt_in`` rather than preserving the NULL grandfather.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    THIRD_PARTY_DOCUMENT_TYPES,
)
from substrate.graph.ops import update_document_gate_columns  # noqa: E402
from substrate.rights.register import VALID_CONTENT_CLASSES  # noqa: E402
from tools.backfill_cc0_remap import _classify_basis as _classify_license_basis  # noqa: E402

TARGET_KEY = "null_content_class_backfill_target"
REASON_KEY = "null_content_class_backfill_reason"
BACKFILLED_AT_KEY = "null_content_class_backfilled_at"
_BACKFILL_KEYS = (TARGET_KEY, REASON_KEY, BACKFILLED_AT_KEY)

BACKFILL_ACTION_TYPE = "corpus.backfill_null_content_class"
_ARXIV_METADATA_SOURCES = {"arxiv", "arxiv_oai_pmh", "arxiv_bulk"}
_T2_T3_TIERS = {"T2", "T2_NON_COMMERCIAL", "t2", "T3", "T3_DEFAULT_UNKNOWN", "t3"}

assert PERSONAL_READING_CONTENT_CLASS in VALID_CONTENT_CLASSES
assert GATED_DEFAULT_CONTENT_CLASS in VALID_CONTENT_CLASSES
assert set(SERVABLE_CONTENT_CLASSES) <= set(VALID_CONTENT_CLASSES)


@dataclass(frozen=True)
class BackfillDecision:
    document_id: str
    target_class: str | None
    reason: str

    @property
    def unresolved(self) -> bool:
        return self.target_class is None


@dataclass(frozen=True)
class BackfillPlan:
    total_null: int
    planned: int
    unresolved: int
    by_target: tuple[tuple[str, int], ...]
    by_reason: tuple[tuple[str, int], ...]
    unresolved_document_ids: tuple[str, ...]


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_metadata(metadata_json: str | None) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        obj = json.loads(metadata_json)
    except (TypeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _write_metadata(con, document_id: str, meta: Mapping[str, Any]) -> None:
    con.execute(
        "UPDATE documents SET metadata = ? WHERE document_id = ?",
        [json.dumps(dict(meta), default=str), document_id],
    )


def _first_nonempty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _is_arxiv_row(document_id: str, source_uri: str | None, meta: Mapping[str, Any]) -> bool:
    source = _first_nonempty(meta.get("source"))
    if source in _ARXIV_METADATA_SOURCES:
        return True
    if _first_nonempty(meta.get("arxiv_id")) or document_id.startswith("doc-arxiv-"):
        return True
    return bool(source_uri and "arxiv.org/" in source_uri)


def _metadata_license_class(meta: Mapping[str, Any]) -> str | None:
    candidate = _first_nonempty(meta.get("license_content_class"), meta.get("content_class"))
    if candidate in VALID_CONTENT_CLASSES:
        return candidate
    return None


def _decide(
    *,
    document_id: str,
    document_type: str | None,
    source_uri: str | None,
    metadata_json: str | None,
    license_basis: str | None,
) -> BackfillDecision:
    meta = _load_metadata(metadata_json)
    if document_type in THIRD_PARTY_DOCUMENT_TYPES:
        return BackfillDecision(
            document_id,
            PERSONAL_READING_CONTENT_CLASS,
            "third_party_personal_ingest",
        )

    if _is_arxiv_row(document_id, source_uri, meta):
        tier = _first_nonempty(meta.get("rights_tier"), meta.get("tier"))
        if tier in _T2_T3_TIERS:
            return BackfillDecision(document_id, GATED_DEFAULT_CONTENT_CLASS, "arxiv_non_t1")

    license_class = _metadata_license_class(meta)
    if license_class:
        return BackfillDecision(document_id, license_class, "metadata_license_content_class")

    basis_class = _classify_license_basis(license_basis)
    if basis_class:
        return BackfillDecision(document_id, basis_class, "book_assets_license_basis")

    return BackfillDecision(document_id, None, "unresolved")


def _scan(con) -> tuple[BackfillPlan, list[tuple[BackfillDecision, str | None]]]:
    rows = con.execute(
        """
        SELECT d.document_id, d.document_type, d.source_uri, d.metadata,
               ba.license_basis
          FROM documents d
          LEFT JOIN (
              SELECT document_id, max(license_basis) AS license_basis
                FROM book_assets
               GROUP BY document_id
          ) ba ON ba.document_id = d.document_id
         WHERE d.content_class IS NULL
         ORDER BY d.document_id
        """
    ).fetchall()

    targets: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    unresolved_ids: list[str] = []
    decisions: list[tuple[BackfillDecision, str | None]] = []
    for document_id, document_type, source_uri, metadata_json, license_basis in rows:
        decision = _decide(
            document_id=document_id,
            document_type=document_type,
            source_uri=source_uri,
            metadata_json=metadata_json,
            license_basis=license_basis,
        )
        decisions.append((decision, metadata_json))
        reasons[decision.reason] += 1
        if decision.target_class is None:
            unresolved_ids.append(document_id)
        else:
            targets[decision.target_class] += 1

    plan = BackfillPlan(
        total_null=len(rows),
        planned=sum(targets.values()),
        unresolved=len(unresolved_ids),
        by_target=tuple(sorted(targets.items())),
        by_reason=tuple(sorted(reasons.items())),
        unresolved_document_ids=tuple(unresolved_ids),
    )
    return plan, decisions


def _apply(
    con,
    decisions: Sequence[tuple[BackfillDecision, str | None]],
    *,
    allow_unresolved_to_gated: bool,
) -> int:
    applied = 0
    for decision, metadata_json in decisions:
        target = decision.target_class
        reason = decision.reason
        if target is None:
            if not allow_unresolved_to_gated:
                continue
            target = GATED_DEFAULT_CONTENT_CLASS
            reason = "unresolved_to_gated_floor"

        meta = _load_metadata(metadata_json)
        meta[TARGET_KEY] = target
        meta[REASON_KEY] = reason
        meta[BACKFILLED_AT_KEY] = _now_iso_z()
        _write_metadata(con, decision.document_id, meta)
        update_document_gate_columns(
            con,
            decision.document_id,
            content_class=target,
            set_content_class=True,
        )
        applied += 1
    return applied


def _emit(plan: BackfillPlan, *, operation: str, applied: int) -> None:
    from substrate.event_log.events import log_event

    log_event(
        "corpus-backfill-null-content-class",
        BACKFILL_ACTION_TYPE,
        payload={
            "operation": operation,
            "rows": applied,
            "total_null": plan.total_null,
            "planned": plan.planned,
            "unresolved": plan.unresolved,
            "by_target": [list(t) for t in plan.by_target],
            "by_reason": [list(t) for t in plan.by_reason],
        },
        role="migration",
    )


def _print_report(plan: BackfillPlan, *, applied: bool, allow_unresolved_to_gated: bool) -> None:
    verb = "APPLIED" if applied else "DRY RUN (nothing written)"
    print(f"NULL content_class backfill — {verb}\n")
    print(f"  NULL documents examined : {plan.total_null}")
    print(f"  planned explicit classes: {plan.planned}")
    print(f"  unresolved              : {plan.unresolved}")
    print("  by target:")
    for target, n in plan.by_target:
        print(f"    {target}: {n}")
    if not plan.by_target:
        print("    (none)")
    print("  by reason:")
    for reason, n in plan.by_reason:
        print(f"    {reason}: {n}")
    if not plan.by_reason:
        print("    (none)")
    if plan.unresolved_document_ids:
        print("  unresolved document_ids:")
        for document_id in plan.unresolved_document_ids[:20]:
            print(f"    {document_id}")
        if len(plan.unresolved_document_ids) > 20:
            print(f"    ... {len(plan.unresolved_document_ids) - 20} more")
    if not applied and plan.total_null:
        extra = " --allow-unresolved-to-gated" if plan.unresolved else ""
        print(f"\n  re-run with --apply{extra} to effect the backfill.")
    if applied and allow_unresolved_to_gated and plan.unresolved:
        print("\n  unresolved rows were moved to restricted_pending_opt_in.")


def _is_prod_db(db_path: str) -> bool:
    from substrate.graph import default_db_path

    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def run(
    db_path: str,
    *,
    apply: bool = False,
    allow_unresolved_to_gated: bool = False,
) -> BackfillPlan:
    if apply:
        with connect_write(db_path, purpose="backfill_null_content_class") as con:
            plan, decisions = _scan(con)
            if plan.unresolved and not allow_unresolved_to_gated:
                raise RuntimeError(
                    "NULL content_class backfill has unresolved rows; inspect the "
                    "dry-run report or pass allow_unresolved_to_gated=True to move "
                    "them to restricted_pending_opt_in."
                )
            applied = _apply(
                con,
                decisions,
                allow_unresolved_to_gated=allow_unresolved_to_gated,
            )
        _emit(plan, operation="apply", applied=applied)
        return plan

    with connect_read(db_path) as con:
        plan, _ = _scan(con)
    return plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.backfill_null_content_class",
        description=(
            "Backfill legacy documents.content_class NULL rows before the SR-07 "
            "fail-closed retrieval flip. Dry-run by default; LOCAL/TEMP DB only."
        ),
    )
    p.add_argument(
        "--db-path",
        required=True,
        help="LOCAL/TEMP DuckDB path (never prod; the prod default is rejected)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="effect the backfill (default is a dry-run report that writes nothing)",
    )
    p.add_argument(
        "--allow-unresolved-to-gated",
        action="store_true",
        help=(
            "with --apply, move rows with no deterministic classification to "
            "restricted_pending_opt_in"
        ),
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if _is_prod_db(args.db_path):
        print(
            "error: --db-path resolves to the prod substrate default; this CLI "
            "may only run against a LOCAL/TEMP DB (prod backfill is operator-gated)",
            file=sys.stderr,
        )
        return 2

    try:
        plan = run(
            args.db_path,
            apply=args.apply,
            allow_unresolved_to_gated=args.allow_unresolved_to_gated,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_report(
        plan,
        applied=args.apply,
        allow_unresolved_to_gated=args.allow_unresolved_to_gated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
