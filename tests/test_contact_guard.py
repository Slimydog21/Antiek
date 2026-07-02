"""SPR-09 M3 — no-email-to-unclaimed contact guard (red-then-green).

Two halves, mirroring the serve-guard rigor pattern:

  1. RUNTIME: ``guarded_send_to_author`` to an UNCLAIMED author is BLOCKED +
     logged, and the underlying ``provider.send`` is NEVER called. Since no
     claim flow exists (SPR-07 unbuilt), EVERY author is unclaimed — so this is
     the universal behaviour today, not an edge case.

  2. SCANNER (red-then-green): the ``contact_guard_check`` AST scanner is clean
     on the real tree (the operator magic-link site is allowlisted), and — when
     pointed at a synthetic tree containing a rogue un-allowlisted
     ``provider.send`` / ``OutboundEmail(`` site — flags exactly that file:line
     while NOT flagging the allowlisted ``auth.py`` operator-magic-link site.
"""

from __future__ import annotations

import logging
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.auth.email_provider import MockEmailProvider, OutboundEmail
from substrate.payouts.contact_guard import (
    ContactBlocked,
    get_author_contact_claim,
    guarded_send_to_author,
    is_author_claimed,
    record_author_contact_claim,
    revoke_author_contact_claim,
)
from tools.lint import contact_guard_check

# ── 1. Runtime guard: unclaimed author is blocked, provider never called ────


def _outbound(to: str = "author@example.org") -> OutboundEmail:
    return OutboundEmail(
        to=to,
        subject="Your paper earned a payout on Antiek",
        text_body="A reader engaged with your paper...",
    )


def test_no_author_is_claimed_today():
    """The SPR-07 plug point is deny-by-default without a claim store."""
    assert is_author_claimed("orcid:0000-0002-1825-0097") is False
    assert is_author_claimed("(2401.00001, 0)") is False


@pytest.fixture
def claim_db():
    with tempfile.TemporaryDirectory(prefix="antiek-author-claims-") as tmp:
        db_path = os.path.join(tmp, "claims.duckdb")
        con = connect_write(db_path, purpose="test_author_contact_claims")
        init_database(con)
        try:
            yield con
        finally:
            con.close()


def test_author_contact_claims_table_starts_denied(claim_db):
    """An initialized real table is still denied until a row explicitly opts in."""
    assert is_author_claimed("orcid:0000-0002-1825-0097", con=claim_db) is False

    claim = record_author_contact_claim(
        claim_db,
        author_ref="orcid:0000-0002-1825-0097",
        evidence={"method": "orcid-oauth"},
    )

    assert claim.contact_opt_in is False
    assert claim.claimed_at is not None
    assert claim.evidence == {"method": "orcid-oauth"}
    assert is_author_claimed("orcid:0000-0002-1825-0097", con=claim_db) is False


def test_author_claim_read_denies_when_table_is_absent():
    """A read predicate must not create tables; missing claim state is deny."""
    with tempfile.TemporaryDirectory(prefix="antiek-author-claims-empty-") as tmp:
        db_path = os.path.join(tmp, "claims.duckdb")
        con = connect_write(db_path, purpose="test_author_contact_claims_absent")
        try:
            assert is_author_claimed("orcid:absent", con=con) is False
        finally:
            con.close()


def test_guarded_send_to_unclaimed_author_is_blocked_and_does_not_call_provider(caplog):
    """RED-THEN-GREEN core: an author send is BLOCKED (raises ContactBlocked),
    is LOGGED, and the underlying provider.send is NEVER invoked. The provider
    is a real MockEmailProvider whose ``sent`` list proves the send did not
    happen."""
    provider = MockEmailProvider(log_to_stdout=False)
    outbound = _outbound()

    with caplog.at_level(logging.WARNING, logger="antiek.payouts.contact_guard"):
        with pytest.raises(ContactBlocked) as exc:
            guarded_send_to_author(
                provider, outbound, author_ref="orcid:0000-0002-1825-0097"
            )

    # The provider was NEVER called — no record landed in its in-memory log.
    assert provider.sent == [], "provider.send must NOT be called for an unclaimed author"
    # The block carries the author + recipient for the audit trail.
    assert exc.value.author_ref == "orcid:0000-0002-1825-0097"
    assert exc.value.to == "author@example.org"
    # The block was logged (never silently swallowed).
    assert any(
        "BLOCKED author-directed email" in rec.message for rec in caplog.records
    ), "the block must be logged"


def test_guard_sends_only_for_claimed_and_contact_opted_in_author(claim_db):
    """A real claim row admits contact only when contact_opt_in is true."""
    record_author_contact_claim(
        claim_db,
        author_ref="orcid:claimed",
        contact_opt_in=True,
        evidence={"method": "signed-magic-link", "version": 1},
    )
    provider = MockEmailProvider(log_to_stdout=False)
    result = guarded_send_to_author(
        provider, _outbound(), author_ref="orcid:claimed", claims_con=claim_db
    )

    persisted = get_author_contact_claim(claim_db, "orcid:claimed")
    assert persisted is not None
    assert persisted.contact_opt_in is True
    assert persisted.contact_opted_in_at is not None
    assert persisted.revoked_at is None
    assert result.blocked is False
    assert result.reason == "author_claimed"
    assert len(provider.sent) == 1
    assert provider.sent[0].email.to == "author@example.org"


def test_guard_blocks_after_author_contact_claim_is_revoked(claim_db):
    record_author_contact_claim(
        claim_db,
        author_ref="orcid:revoked",
        contact_opt_in=True,
    )
    revoke_author_contact_claim(claim_db, author_ref="orcid:revoked")
    provider = MockEmailProvider(log_to_stdout=False)

    with pytest.raises(ContactBlocked):
        guarded_send_to_author(
            provider,
            _outbound(),
            author_ref="orcid:revoked",
            claims_con=claim_db,
        )

    persisted = get_author_contact_claim(claim_db, "orcid:revoked")
    assert persisted is not None
    assert persisted.contact_opt_in is False
    assert persisted.revoked_at is not None
    assert provider.sent == []


# ── 2. The contact-guard scanner: clean on the tree + has teeth ─────────────


def test_scanner_reports_zero_violations_on_the_current_tree():
    """The boundary holds even under a pytest-only run: invoke the scanner
    programmatically and assert ZERO violations. The operator magic-link send in
    interfaces/research/api/auth.py is allowlisted, so a clean tree is the
    expected state."""
    violations = contact_guard_check.find_violations()
    assert violations == [], (
        "outbound-email send / OutboundEmail construction outside the guard:\n"
        + "\n".join(violations)
    )


def test_scanner_catches_an_injected_unallowlisted_send_at_exact_file_line():
    """RIGOR #3 — prove the scanner is not vacuously green: a synthetic tree with
    a rogue ``provider.send(OutboundEmail(...))`` in a NON-allowlisted module is
    flagged at exactly that file:line, while the allowlisted operator
    magic-link auth.py site (built with the same call shape) is NOT flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # A non-allowed, non-test module that emails an author directly.
        offender = root / "substrate" / "outreach" / "notify_author.py"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            textwrap.dedent(
                """\
                from substrate.auth.email_provider import (
                    OutboundEmail,
                    get_email_provider,
                )

                def notify(author_email):
                    provider = get_email_provider()
                    provider.send(OutboundEmail(to=author_email, subject="x", text_body="y"))
                """
            ),
            encoding="utf-8",
        )
        # The ALLOWLISTED operator magic-link route, built with the SAME shape,
        # must NOT flag (operator-self mail, not author-directed). Round-2: the
        # allow is FUNCTION-SCOPED, so the site must live in one of the allowed
        # functions (``auth_request`` here) to be exempt.
        auth = root / "interfaces" / "research" / "api" / "auth.py"
        auth.parent.mkdir(parents=True)
        auth.write_text(
            textwrap.dedent(
                """\
                from substrate.auth.email_provider import (
                    OutboundEmail,
                    get_email_provider,
                )

                async def auth_request(operator_email):
                    provider = get_email_provider()
                    provider.send(OutboundEmail(to=operator_email, subject="Sign in", text_body="link"))
                """
            ),
            encoding="utf-8",
        )
        # A test file must NOT flag — tests exercise the provider directly.
        test_file = root / "tests" / "test_x.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "from substrate.auth.email_provider import OutboundEmail\n"
            "def test_y(provider):\n"
            "    provider.send(OutboundEmail(to='t', subject='s', text_body='b'))\n",
            encoding="utf-8",
        )

        violations = contact_guard_check.find_violations(root=root)

    flagged_paths = {line.split(":", 1)[0] for line in violations}
    # ONLY the rogue author-notify module is flagged — never the allowlisted
    # auth.py operator site, never the test file.
    assert flagged_paths == {"substrate/outreach/notify_author.py"}, violations
    # The rogue site is flagged on its exact construction/send line (line 8, the
    # provider.send(OutboundEmail(...)) statement). Both the send and the
    # construction land on the same line; assert that exact line is reported.
    rogue_lines = {
        int(v.split(":")[1])
        for v in violations
        if v.startswith("substrate/outreach/notify_author.py:")
    }
    assert 8 in rogue_lines, violations


def test_scanner_flags_a_rogue_send_inside_auth_py_not_in_an_allowed_function():
    """RIGOR #3 (round-2 function-scoping) — the auth.py allow is per-FUNCTION, not
    whole-file: a NEW ``provider.send(OutboundEmail(...))`` / ``OutboundEmail(...)``
    added to auth.py in a function OTHER than the known magic-link ones
    (``_format_magic_link_email`` / ``auth_request``) IS flagged. The known sites
    in their allowed functions are NOT flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auth = root / "interfaces" / "research" / "api" / "auth.py"
        auth.parent.mkdir(parents=True)
        auth.write_text(
            textwrap.dedent(
                """\
                from substrate.auth.email_provider import (
                    OutboundEmail,
                    get_email_provider,
                )

                def _format_magic_link_email(email, link):
                    return OutboundEmail(to=email, subject="Sign in", text_body=link)

                async def auth_request(email):
                    provider = get_email_provider()
                    provider.send(_format_magic_link_email(email, "l"))

                def secretly_email_an_author(author_email):
                    # ROGUE: a NEW email path snuck into auth.py — must be flagged.
                    provider = get_email_provider()
                    provider.send(OutboundEmail(to=author_email, subject="x", text_body="y"))
                """
            ),
            encoding="utf-8",
        )

        violations = contact_guard_check.find_violations(root=root)

    # The rogue function's construction + send are flagged (BOTH on line 16, the
    # provider.send(OutboundEmail(...)) statement); the two known magic-link sites
    # (in their allowed functions) are NOT.
    rogue_lines = {
        int(v.split(":")[1])
        for v in violations
        if v.startswith("interfaces/research/api/auth.py:")
    }
    assert rogue_lines == {16}, violations
    # The allowed OutboundEmail (line 6) and the allowed send (line 10) are absent.
    assert 6 not in rogue_lines and 10 not in rogue_lines, violations
