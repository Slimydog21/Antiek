"""Speak SPR-07 — economics matrix + publishing modes tests.

Rigor #3: each of the four cells, the binding rule (public + private
invitations → algorithmic split, creator can't pocket it), the flip
mid-project (consent re-check; forward split), a contributor who didn't
consent to publish (excluded, not silently kept), and prompt-inference
cost on a private book. There is NO creator-override knob.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import economics_mode as em
from substrate.speak import invitations, project
from substrate.speak.consent import ConsentScope, record_consent
from substrate.speak.economics_mode import MARGIN_PRIVATE_PUBLISHED, MARGIN_PUBLIC, resolve_policy
from substrate.speak.schema import ensure_speak_schema


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-matrix-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="matrix_test")


# ── M1 mode model — all four cells resolve ──────────────────────────────


@pytest.mark.parametrize("invitation,publishing", [
    ("private", "never_published"),
    ("private", "public"),
    ("public", "public"),
    ("public", "never_published"),
])
def test_all_four_cells_resolve(invitation, publishing):
    policy = resolve_policy(invitation, publishing)
    assert policy.invitation == invitation
    assert policy.publishing == publishing


# ── M2 margin policy ────────────────────────────────────────────────────


def test_public_margin_is_ten_percent():
    assert resolve_policy("private", "public").inference_margin == MARGIN_PUBLIC
    assert resolve_policy("public", "public").inference_margin == MARGIN_PUBLIC


def test_never_published_margin_is_fifty_percent():
    assert resolve_policy("private", "never_published").inference_margin == MARGIN_PRIVATE_PUBLISHED


def test_billed_inference_applies_margin():
    policy = resolve_policy("private", "never_published")
    # 50% margin on $1.00 base → $1.50.
    assert em.billed_inference_cost(Decimal("1.00"), policy) == Decimal("1.500000")


# ── M3 split policy + the binding rule ──────────────────────────────────


def test_public_always_splits_even_private_invitations():
    # The binding rule: private invitations + public publishing still
    # routes the algorithmic 70% split — the creator can't pocket it.
    policy = resolve_policy("private", "public")
    assert policy.split_applies is True


def test_private_never_published_does_not_split():
    policy = resolve_policy("private", "never_published")
    assert policy.split_applies is False
    assert policy.creator_carries_cost is True


def test_no_creator_override_knob():
    # There is no way to construct a public policy that doesn't split —
    # resolve_policy takes only the two dimensions, no override.
    import inspect
    params = set(inspect.signature(resolve_policy).parameters)
    assert params == {"invitation", "publishing"}
    # And every public cell splits.
    for inv in ("private", "public"):
        assert resolve_policy(inv, "public").split_applies is True


# ── M4 cost-carry for private-never-published ───────────────────────────


def test_creator_carries_inference_plus_prompt_and_physical():
    policy = resolve_policy("private", "never_published")
    cost = em.creator_cost(
        policy,
        base_inference_cost_usd=Decimal("2.00"),     # ×1.50 margin = 3.00
        prompt_inference_cost_usd=Decimal("0.50"),   # prompting the book
        physical_cost_usd=Decimal("12.00"),          # paperback
    )
    assert cost == Decimal("15.500000")


def test_public_creator_carries_nothing_here():
    policy = resolve_policy("public", "public")
    assert em.creator_cost(policy, base_inference_cost_usd=Decimal("2.00")) == Decimal("0")


# ── M5 mode transitions (flip + consent re-check) ───────────────────────


def test_flip_switches_economics_and_rechecks_consent(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography",
                                   publish_intent="private_never_published")
        # Two contributors: one consented to publish, one did not.
        iv_yes = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="y@x.com")
        iv_no = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="n@x.com")
        record_consent(con, interview_id=iv_yes.interview_id,
                       scopes=[ConsentScope.RECORD, ConsentScope.PUBLISH])
        record_consent(con, interview_id=iv_no.interview_id, scopes=[ConsentScope.RECORD])

        # Before flip: never-published economics.
        assert em.policy_for_project(con, p.project_id).split_applies is False

        result = em.flip_to_public(con, project_id=p.project_id)
        # After flip: public economics (10% margin, split applies).
        assert result.policy.inference_margin == MARGIN_PUBLIC
        assert result.policy.split_applies is True
        # The non-consenting contributor is surfaced for EXCLUSION, not
        # silently kept.
        assert iv_no.interview_id in result.contributors_without_publish_consent
        assert iv_yes.interview_id not in result.contributors_without_publish_consent
        assert em.publish_consent_complete(con, p.project_id) is False


def test_flip_consent_complete_when_all_consent(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        iv = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="y@x.com")
        record_consent(con, interview_id=iv.interview_id,
                       scopes=[ConsentScope.RECORD, ConsentScope.PUBLISH])
        result = em.flip_to_public(con, project_id=p.project_id)
        assert result.contributors_without_publish_consent == ()
        assert em.publish_consent_complete(con, p.project_id) is True
