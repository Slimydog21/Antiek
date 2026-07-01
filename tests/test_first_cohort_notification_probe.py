from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.ip_holders import (
    FIRST_COHORT_PUBLISHERS,
    claim,
    create_pre_onboarded,
    mark_invited,
    opt_out,
)
from tools.ops import first_cohort_notification_probe


@pytest.fixture
def cohort_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "cohort.duckdb"
    con = connect_write(str(db_path), purpose="first_cohort_notification_probe_test")
    init_database(con)
    con.close()
    return db_path


def _decision(tmp_path: Path) -> Path:
    path = tmp_path / "docs/decisions/g2-lawyer-review.md"
    path.parent.mkdir(parents=True)
    path.write_text("# G2 Lawyer Review\n\n**Decided:** 2026-07-01\n", encoding="utf-8")
    return path


def _seed_notified_first_cohort(db_path: Path) -> None:
    con = connect_write(str(db_path), purpose="seed_first_cohort")
    try:
        for publisher in FIRST_COHORT_PUBLISHERS:
            holder_id = create_pre_onboarded(
                con,
                display_name=publisher,
                legal_contact_email=f"legal@{publisher.lower().replace(' ', '')}.example",
            )
            mark_invited(con, holder_id)
    finally:
        con.close()


def test_first_cohort_notification_probe_passes_invited_cohort(
    cohort_db: Path,
    tmp_path: Path,
):
    _seed_notified_first_cohort(cohort_db)
    decision = _decision(tmp_path)

    result = first_cohort_notification_probe.probe_first_cohort_notifications(
        db_path=cohort_db,
        decision_path=decision,
    )

    assert result.status == "PASS"
    assert {publisher.status for publisher in result.publishers} == {"invited"}
    assert all(publisher.notification_sent_at for publisher in result.publishers)
    assert result.does_not_close_oa015 is True


def test_first_cohort_notification_probe_accepts_claimed_or_opted_out_after_notification(
    cohort_db: Path,
    tmp_path: Path,
):
    con = connect_write(str(cohort_db), purpose="seed_first_cohort_statuses")
    try:
        mit = create_pre_onboarded(
            con,
            display_name="MIT Press",
            legal_contact_email="legal@mitpress.example",
        )
        mark_invited(con, mit)
        claim(con, mit, stripe_connect_account_id="acct_mit")

        cambridge = create_pre_onboarded(
            con,
            display_name="Cambridge University Press",
            legal_contact_email="legal@cambridge.example",
        )
        mark_invited(con, cambridge)
        opt_out(con, cambridge)

        princeton = create_pre_onboarded(
            con,
            display_name="Princeton University Press",
            legal_contact_email="legal@princeton.example",
        )
        mark_invited(con, princeton)
    finally:
        con.close()

    result = first_cohort_notification_probe.probe_first_cohort_notifications(
        db_path=cohort_db,
        decision_path=_decision(tmp_path),
    )

    assert result.status == "PASS"
    assert {publisher.status for publisher in result.publishers} == {
        "claimed",
        "opted_out",
        "invited",
    }


def test_first_cohort_notification_probe_fails_without_g2_decision(
    cohort_db: Path,
    tmp_path: Path,
):
    _seed_notified_first_cohort(cohort_db)

    result = first_cohort_notification_probe.probe_first_cohort_notifications(
        db_path=cohort_db,
        decision_path=tmp_path / "missing.md",
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["g2_lawyer_review_filed"].passed is False


def test_first_cohort_notification_probe_fails_missing_rows(
    cohort_db: Path,
    tmp_path: Path,
):
    decision = _decision(tmp_path)

    result = first_cohort_notification_probe.probe_first_cohort_notifications(
        db_path=cohort_db,
        decision_path=decision,
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["first_cohort_rows_exist"].passed is False
    assert "MIT Press" in checks["first_cohort_rows_exist"].detail


def test_first_cohort_notification_probe_fails_pre_onboarded_without_timestamp(
    cohort_db: Path,
    tmp_path: Path,
):
    con = connect_write(str(cohort_db), purpose="seed_pre_onboarded_first_cohort")
    try:
        for publisher in FIRST_COHORT_PUBLISHERS:
            create_pre_onboarded(
                con,
                display_name=publisher,
                legal_contact_email="legal@example.com",
            )
    finally:
        con.close()

    result = first_cohort_notification_probe.probe_first_cohort_notifications(
        db_path=cohort_db,
        decision_path=_decision(tmp_path),
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["first_cohort_notified_status"].passed is False
    assert checks["first_cohort_notification_timestamps"].passed is False


def test_first_cohort_notification_probe_json_cli(
    cohort_db: Path,
    tmp_path: Path,
    capsys,
):
    _seed_notified_first_cohort(cohort_db)
    decision = _decision(tmp_path)

    exit_code = first_cohort_notification_probe.main([
        "--db-path",
        str(cohort_db),
        "--decision-path",
        str(decision),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert len(payload["publishers"]) == 3
    assert payload["does_not_close_oa015"] is True
