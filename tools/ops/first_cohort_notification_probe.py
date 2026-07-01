"""Operator probe for OA-015 first-cohort publisher notification evidence.

OA-015 closes only after OA-001/G2 counsel review is filed and the operator
sends the first-cohort publisher notification emails. This probe validates the
mechanical evidence in ``ip_holders``: every canonical first-cohort publisher
has crossed the notification boundary and has ``notification_sent_at`` set.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from runtime.db_lock import connect_write
from substrate.ip_holders import FIRST_COHORT_PUBLISHERS

DEFAULT_DECISION_PATH = Path("docs/decisions/g2-lawyer-review.md")
NOTIFIED_STATUSES = frozenset({"invited", "claimed", "opted_out"})


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PublisherNotificationEvidence:
    display_name: str
    status: str | None
    notification_sent_at: str | None
    legal_contact_email_present: bool


@dataclass(frozen=True)
class FirstCohortNotificationProbeResult:
    status: str
    db_path: str
    decision_path: str
    publishers: list[PublisherNotificationEvidence]
    checks: list[ProbeCheck]
    does_not_close_oa015: bool = True


def _fetch_publisher(con, display_name: str) -> PublisherNotificationEvidence:
    row = con.execute(
        """
        SELECT status, notification_sent_at, legal_contact_email
        FROM ip_holders
        WHERE display_name = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [display_name],
    ).fetchone()
    if row is None:
        return PublisherNotificationEvidence(
            display_name=display_name,
            status=None,
            notification_sent_at=None,
            legal_contact_email_present=False,
        )
    status, notification_sent_at, legal_contact_email = row
    return PublisherNotificationEvidence(
        display_name=display_name,
        status=str(status) if status is not None else None,
        notification_sent_at=str(notification_sent_at) if notification_sent_at else None,
        legal_contact_email_present=bool(legal_contact_email),
    )


def _cohort_checks(
    publishers: list[PublisherNotificationEvidence],
) -> list[ProbeCheck]:
    missing_rows = [
        publisher.display_name
        for publisher in publishers
        if publisher.status is None
    ]
    not_notified = [
        f"{publisher.display_name}:{publisher.status}"
        for publisher in publishers
        if publisher.status not in NOTIFIED_STATUSES
    ]
    missing_timestamps = [
        publisher.display_name
        for publisher in publishers
        if publisher.notification_sent_at is None
    ]
    missing_legal_contacts = [
        publisher.display_name
        for publisher in publishers
        if not publisher.legal_contact_email_present
    ]
    return [
        ProbeCheck(
            name="first_cohort_rows_exist",
            passed=not missing_rows,
            detail="all first-cohort rows present"
            if not missing_rows
            else "missing=" + ", ".join(missing_rows),
        ),
        ProbeCheck(
            name="first_cohort_notified_status",
            passed=not not_notified,
            detail="all first-cohort rows are invited/claimed/opted_out"
            if not not_notified
            else "not_notified=" + ", ".join(not_notified),
        ),
        ProbeCheck(
            name="first_cohort_notification_timestamps",
            passed=not missing_timestamps,
            detail="all notification_sent_at timestamps populated"
            if not missing_timestamps
            else "missing=" + ", ".join(missing_timestamps),
        ),
        ProbeCheck(
            name="first_cohort_legal_contacts",
            passed=not missing_legal_contacts,
            detail="all legal contact emails populated"
            if not missing_legal_contacts
            else "missing=" + ", ".join(missing_legal_contacts),
        ),
    ]


def probe_first_cohort_notifications(
    *,
    db_path: Path,
    decision_path: Path = DEFAULT_DECISION_PATH,
) -> FirstCohortNotificationProbeResult:
    checks = [
        ProbeCheck(
            name="g2_lawyer_review_filed",
            passed=decision_path.exists(),
            detail=(
                f"path={decision_path}"
                if decision_path.exists()
                else f"missing prerequisite decision: {decision_path}"
            ),
        ),
        ProbeCheck(
            name="db_path_exists",
            passed=db_path.exists(),
            detail=f"path={db_path}" if db_path.exists() else f"missing db path: {db_path}",
        ),
    ]
    if not db_path.exists():
        return FirstCohortNotificationProbeResult(
            status="FAIL",
            db_path=str(db_path),
            decision_path=str(decision_path),
            publishers=[],
            checks=checks,
        )

    con = connect_write(str(db_path), purpose="first_cohort_notification_probe")
    try:
        publishers = [
            _fetch_publisher(con, display_name)
            for display_name in FIRST_COHORT_PUBLISHERS
        ]
    finally:
        con.close()

    checks.extend(_cohort_checks(publishers))
    return FirstCohortNotificationProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        db_path=str(db_path),
        decision_path=str(decision_path),
        publishers=publishers,
        checks=checks,
    )


def format_text(result: FirstCohortNotificationProbeResult) -> str:
    lines = [
        f"first-cohort-notification-probe: {result.status}",
        f"db_path: {result.db_path}",
        f"decision_path: {result.decision_path}",
    ]
    for publisher in result.publishers:
        lines.append(
            "publisher: "
            f"{publisher.display_name} "
            f"status={publisher.status or ''} "
            f"notification_sent_at={publisher.notification_sent_at or ''} "
            f"legal_contact_email_present={publisher.legal_contact_email_present}",
        )
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa015_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate OA-015 first-cohort publisher notification evidence. "
            "Does not send email or close OA-015 by itself."
        )
    )
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="Path to the production DuckDB containing ip_holders.",
    )
    parser.add_argument(
        "--decision-path",
        type=Path,
        default=DEFAULT_DECISION_PATH,
        help=f"G2 lawyer-review prerequisite. Default: {DEFAULT_DECISION_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_first_cohort_notifications(
        db_path=args.db_path.expanduser().resolve(),
        decision_path=args.decision_path.expanduser().resolve(),
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
