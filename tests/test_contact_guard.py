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
import tempfile
import textwrap
from pathlib import Path

import pytest

from substrate.auth.email_provider import MockEmailProvider, OutboundEmail
from substrate.payouts.contact_guard import (
    ContactBlocked,
    guarded_send_to_author,
    is_author_claimed,
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
    """The SPR-07 plug point is hardwired deny-all: no claim flow exists, so no
    author is ever claimed. If this ever returns True without a real claim table
    behind it, M3's deny-by-default guarantee is silently broken."""
    assert is_author_claimed("orcid:0000-0002-1825-0097") is False
    assert is_author_claimed("(2401.00001, 0)") is False


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


def test_guard_would_send_only_if_a_claim_existed(monkeypatch):
    """The guard's allow-path is reachable ONLY when ``is_author_claimed`` returns
    True. We monkeypatch the predicate (simulating a future SPR-07 claim) to
    prove the seam works: a claimed author's send goes through and is recorded.
    This documents that the deny is in the PREDICATE, not a hard wall — SPR-07
    flips exactly one function."""
    monkeypatch.setattr(
        "substrate.payouts.contact_guard.is_author_claimed", lambda _ref: True
    )
    provider = MockEmailProvider(log_to_stdout=False)
    result = guarded_send_to_author(
        provider, _outbound(), author_ref="orcid:claimed"
    )
    assert result.blocked is False
    assert result.reason == "author_claimed"
    assert len(provider.sent) == 1
    assert provider.sent[0].email.to == "author@example.org"


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
