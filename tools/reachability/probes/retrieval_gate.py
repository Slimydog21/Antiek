#!/usr/bin/env python3
"""Retrieval-gate reachability probe — Antiek Convergence SPR-03 (M3).

The §9.0 retrieval gate (``substrate/graph/retrieval_gate.py``, consolidated by
#65) is the strategically load-bearing layer: it is what keeps a restricted or
owner-only chunk body from leaving the product. Every OTHER guard on it asserts
CODE (a unit test on ``is_chunk_body_withheld``, the drift lint, the uniqueness
lint). This probe is the only gate that asserts the OUTCOME on the REAL HTTP
path: that a withheld chunk's BODY does not leave ``GET /chunks/{id}`` when the
app is booted through the production ``create_app()`` factory.

Why outcome-not-code (the README "fixture-injection anti-pattern"): a green unit
test on the helper proves the helper is correct; it does NOT prove the helper is
WIRED into the route a frontend actually calls. The flywheel shipped dead for
exactly this reason — a correct brick, never reached from the product. This probe
seeds chunks, drives the real route, and reads the response body.

What it drives (NO retrieval_substrate= injection, NO register_providers=False,
NO stubbed providers — the bare prod factory):

    create_app()                       # the production factory
      seed via insert_document/insert_chunk into the probe's isolated temp DB
      -> GET /chunks/{restricted_id}   assert body WITHHELD, label "restricted"
      -> GET /chunks/{personal_id}     assert body WITHHELD, label "personal_readable"
      -> GET /chunks/{null_id}         assert body SERVED   (legacy grandfathered)
      -> GET /chunks/{unknown_id}      assert OUTCOME + record the fail-open finding

Restricted + personal_reading are the two non-privileged-withheld classes the
gate exists to stop; NULL is the grandfathered legacy class that MUST still
serve (we do NOT over-assert NULL as withheld — that would be a false gate).

────────────────────────────────────────────────────────────────────────────
UNKNOWN-CLASS FAIL-OPEN (rigor/honesty — VERIFIED, see
docs/decisions/retrieval-gate-unknown-class-fail-open.md). A content_class that
is in NEITHER gate set (a future/new class, e.g. ``"some_future_class_v2"``) is
SERVED by ``GET /chunks/{id}`` — ``is_chunk_body_withheld`` returns
``(False, None)`` for anything not explicitly in PERSONAL_ONLY / RESTRICTED.
This is fail-OPEN, and it is symmetric with the SQL gate: the SQL clause is
``content_class IS NULL OR content_class NOT IN (<excluded>)``, so an unknown
class also passes ``NOT IN`` and is served on chunk search. (NOTE: this CORRECTS
the SPR-03 brief's premise that the SQL gate "fail-CLOSES on an unknown class via
NOT IN → excluded" — it does not; the verified behaviour is that BOTH paths
fail-OPEN on an unknown class.) The probe does NOT treat unknown-served as a
failure (changing the withhold polarity to deny-by-default is a §9 operator
design call, OUT OF SCOPE for SPR-03); it asserts the observed outcome and
surfaces it as a recorded finding so a future class added without updating BOTH
the frozensets and the SQL excluded set cannot silently leak unnoticed.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import tempfile

from tools.reachability.probe_runner import ProbeResult

# An explicit content_class that is in NEITHER gate set. Used to exercise the
# unknown/new-class fail-open path on the REAL HTTP route. Must NOT match
# restricted_pending_opt_in / personal_reading / any servable class so the
# behaviour observed is the "not enumerated anywhere" path specifically.
_UNKNOWN_CONTENT_CLASS = "acv_spr03_unknown_future_class"


def _probe() -> ProbeResult:
    # Isolate ALL substrate writes to per-PID temp paths so the probe never
    # touches the live shared DuckDB (held under the --workers 1 single-writer
    # lock) and reads a clean DB it alone seeded. Same isolation contract as the
    # flywheel probe (README "isolate your writes").
    pid = os.getpid()
    tmp_root = tempfile.mkdtemp(prefix=f"antiek-gate-probe-{pid}-")
    tmp_db = os.path.join(tmp_root, f"antiek-gate-probe-{pid}.db")
    tmp_events = os.path.join(tmp_root, "events")
    os.makedirs(tmp_events, exist_ok=True)

    _provider_keys = (
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "HERMES_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTIEK_OPERATOR_TOKEN",
    )
    saved = {
        k: os.environ.get(k)
        for k in ("ANTIEK_DUCKDB_PATH", "ANTIEK_RESEARCH_EVENTS_DIR", *_provider_keys)
    }
    os.environ["ANTIEK_DUCKDB_PATH"] = tmp_db
    os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = tmp_events
    # Defence-in-depth: keep paid providers OUT of the boot so a leaky path
    # fails fast rather than spending operator credentials.
    for key in _provider_keys:
        os.environ[key] = ""

    try:
        # ── seed chunks of each gate class into the isolated DB ──
        # Mirrors tests/test_sprint11_api.py::_seed_chunk exactly (the sanctioned
        # graph-ops insert path), so the probe exercises the same rows shape the
        # gate is unit-tested against. NULL + the unknown class use a NON-third-
        # party document_type (academic_paper) so insert_document does NOT default
        # content_class to personal_reading (the deny-by-default defaulting only
        # fires for THIRD_PARTY_DOCUMENT_TYPES with content_class=None); the
        # explicit unknown class beats the default by contract.
        try:
            from runtime.db_lock import connect_write
            from substrate.graph.ops import insert_chunk, insert_document
            from substrate.graph.schema import init_database_at_path

            init_database_at_path(tmp_db)
            seeded: dict[str, str] = {}
            with connect_write(tmp_db, purpose="acv-spr03-gate-probe") as con:
                insert_document(
                    con, document_id="probe-restricted", source_tier=2,
                    document_type="book", title="Restricted Doc",
                    content_class="restricted_pending_opt_in", on_conflict="ignore",
                )
                seeded["restricted"] = insert_chunk(
                    con, document_id="probe-restricted", chunk_index=0,
                    text="RESTRICTED-BODY-must-not-be-served", section_path="p.1",
                )
                insert_document(
                    con, document_id="probe-personal", source_tier=2,
                    document_type="book", title="Personal Doc",
                    content_class="personal_reading", on_conflict="ignore",
                )
                seeded["personal"] = insert_chunk(
                    con, document_id="probe-personal", chunk_index=0,
                    text="PERSONAL-BODY-owner-only", section_path="p.1",
                )
                insert_document(
                    con, document_id="probe-null", source_tier=2,
                    document_type="academic_paper", title="Legacy NULL Doc",
                    content_class=None, on_conflict="ignore",
                )
                seeded["null"] = insert_chunk(
                    con, document_id="probe-null", chunk_index=0,
                    text="LEGACY-NULL-BODY-grandfathered-served", section_path="p.1",
                )
                insert_document(
                    con, document_id="probe-unknown", source_tier=2,
                    document_type="academic_paper", title="Unknown-Class Doc",
                    content_class=_UNKNOWN_CONTENT_CLASS, on_conflict="ignore",
                )
                seeded["unknown"] = insert_chunk(
                    con, document_id="probe-unknown", chunk_index=0,
                    text="UNKNOWN-CLASS-BODY", section_path="p.1",
                )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"could not seed gate fixtures: {type(exc).__name__}: {exc}",
                failure_mode="error",
            )

        # ── boot the app the PRODUCTION way (failure mode: boot_fail) ──
        try:
            from fastapi.testclient import TestClient

            from interfaces.research.api.app import create_app

            app = create_app()  # NO retrieval_substrate=, NO register_providers=False
            client = TestClient(app)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                reason=f"create_app() failed to boot: {type(exc).__name__}: {exc}",
                failure_mode="boot_fail",
            )

        def _get(chunk_id: str) -> tuple[int, dict]:
            r = client.get(f"/chunks/{chunk_id}")
            try:
                return r.status_code, r.json()
            except Exception:  # noqa: BLE001
                return r.status_code, {}

        # ── WITHHELD: restricted body must NOT leave the endpoint ──
        code, body = _get(seeded["restricted"])
        if code == 404:
            return ProbeResult(
                ok=False,
                reason="GET /chunks/{id} 404'd — the chunk route moved/renamed",
                failure_mode="route_404",
            )
        if code != 200:
            return ProbeResult(
                ok=False,
                reason=f"GET /chunks (restricted) -> {code}: {str(body)[:160]}",
                failure_mode="feature_dead",
            )
        if body.get("servable") is not False or body.get("text") != "":
            return ProbeResult(
                ok=False,
                reason=(
                    "restricted chunk BODY LEAKED via GET /chunks: "
                    f"servable={body.get('servable')!r} text={body.get('text')!r}. "
                    "The §9.0 gate is not reached on the real HTTP path "
                    "(is_chunk_body_withheld not applied at app.py:2226)."
                ),
                failure_mode="feature_dead",
            )
        if body.get("servability") != "restricted":
            return ProbeResult(
                ok=False,
                reason=(
                    "restricted chunk withheld but with WRONG label "
                    f"{body.get('servability')!r} (expected 'restricted')"
                ),
                failure_mode="feature_dead",
            )

        # ── WITHHELD: personal_reading body must NOT leave the endpoint ──
        code, body = _get(seeded["personal"])
        if code != 200:
            return ProbeResult(
                ok=False,
                reason=f"GET /chunks (personal) -> {code}: {str(body)[:160]}",
                failure_mode="feature_dead",
            )
        if body.get("servable") is not False or body.get("text") != "":
            return ProbeResult(
                ok=False,
                reason=(
                    "personal_reading chunk BODY LEAKED via GET /chunks: "
                    f"servable={body.get('servable')!r} text={body.get('text')!r}. "
                    "Owner-only content reached a non-privileged HTTP path."
                ),
                failure_mode="feature_dead",
            )
        if body.get("servability") != "personal_readable":
            return ProbeResult(
                ok=False,
                reason=(
                    "personal_reading chunk withheld but with WRONG label "
                    f"{body.get('servability')!r} (expected 'personal_readable')"
                ),
                failure_mode="feature_dead",
            )

        # ── SERVED: NULL/legacy must STILL serve (do NOT over-assert withheld) ──
        code, body = _get(seeded["null"])
        if code != 200:
            return ProbeResult(
                ok=False,
                reason=f"GET /chunks (null) -> {code}: {str(body)[:160]}",
                failure_mode="feature_dead",
            )
        if body.get("servable") is not True or "LEGACY-NULL-BODY" not in (body.get("text") or ""):
            return ProbeResult(
                ok=False,
                reason=(
                    "NULL/legacy chunk was WITHHELD when it must be grandfathered-"
                    f"served: servable={body.get('servable')!r} "
                    f"text={body.get('text')!r}. A gate that over-withholds NULL "
                    "hides the operator's own legacy research — the gate must serve "
                    "NULL on every path (retrieval_gate docstring + "
                    "test_get_chunk_null_content_class_grandfathered)."
                ),
                failure_mode="feature_dead",
            )

        # ── UNKNOWN class: assert the OBSERVED outcome (fail-open) + surface it ──
        # This is NOT a withhold assertion — changing the polarity to deny-by-
        # default is a §9 operator design call (OUT OF SCOPE). We assert the
        # VERIFIED current behaviour so a regression in EITHER direction is
        # caught, and we surface the fail-open as an honest finding (the §9
        # leak risk if a future class is added without updating both paths).
        code, body = _get(seeded["unknown"])
        if code != 200:
            return ProbeResult(
                ok=False,
                reason=f"GET /chunks (unknown) -> {code}: {str(body)[:160]}",
                failure_mode="feature_dead",
            )
        unknown_served = (
            body.get("servable") is True
            and "UNKNOWN-CLASS-BODY" in (body.get("text") or "")
        )
        if not unknown_served:
            # The behaviour CHANGED (gate now withholds an unknown class). That is
            # a deny-by-default flip — a §9 design change. Surface it as a finding
            # rather than silently green; the probe's documented invariant is that
            # the unknown class is SERVED today (fail-open). A flip should land WITH
            # an updated decision note, not as a probe surprise.
            return ProbeResult(
                ok=False,
                reason=(
                    "unknown content_class is now WITHHELD on GET /chunks "
                    f"(servable={body.get('servable')!r} "
                    f"servability={body.get('servability')!r}) — the gate's "
                    "fail-OPEN-on-unknown polarity (verified SPR-03, "
                    "docs/decisions/retrieval-gate-unknown-class-fail-open.md) "
                    "appears to have FLIPPED to deny-by-default. That is a §9 "
                    "design change: update the decision note + this probe's "
                    "documented invariant deliberately, do not let it land as a "
                    "probe surprise."
                ),
                failure_mode="feature_dead",
            )

        # All outcomes held: withheld classes withheld, NULL served, unknown
        # served (the documented + verified fail-open). REACHABLE.
        return ProbeResult(ok=True, failure_mode="reachable")
    finally:
        # Restore env (the runner may run more probes after this one).
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        import shutil

        shutil.rmtree(tmp_root, ignore_errors=True)


# Imported lazily so this top-level import is cheap; build the descriptor here.
from tools.reachability.probe_runner import Probe  # noqa: E402

PROBE = Probe(
    id="retrieval_gate",
    feature="retrieval gate (§9.0 withhold restricted/personal body on GET /chunks)",
    run=_probe,
)
