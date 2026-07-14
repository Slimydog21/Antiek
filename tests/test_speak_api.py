"""Speak REST surface — end-to-end journey + gate-refusal tests.

Exercises the wired router (via the real create_app) over a tmp DB: the
full operator + invitee journey from project creation to a public,
corroborated, monetised publication + a physical-book quote — and that
every gate refuses with the right HTTP status. This is the test that
lets the speak-biography e2e un-skip: the surface now exists.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.speak_routes as speak_routes
from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    # Open auth (operator env unset) + hermetic embedding for the
    # voice-note answer ingest.
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr("acquisition.voice.adapter.default_embedding_provider",
                        lambda: StubEmbedding())
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _invite_and_attest(client, project_id, email, claim_text, subject="the-dad"):
    """Invite an interviewee, consent, and record one third-party claim."""
    iv = client.post(f"/speak/projects/{project_id}/invites",
                     json={"informant_email": email}).json()
    interview_id = iv["interview_id"]
    r = client.post(f"/speak/interviews/{interview_id}/consent",
                    json={"scopes": ["record", "attribute", "publish"]})
    assert r.status_code == 200
    r = client.post(f"/speak/interviews/{interview_id}/claims",
                    json={"text": claim_text, "about_subject": True, "subject_ref": subject})
    assert r.status_code == 201, r.text
    return interview_id


# ── full journey ────────────────────────────────────────────────────────


def test_full_operator_journey_to_public_publish(client, monkeypatch):
    # 1. Create a will-be-public project about a deceased subject.
    r = client.post("/speak/projects", json={
        "title": "Dad's biography", "subject_ref": "the-dad",
        "subject_status": "deceased", "publish_intent": "will_be_public",
    })
    assert r.status_code == 201, r.text
    project_id = r.json()["project_id"]

    # 2. Economics: public ⇒ algorithmic split, 10% margin.
    econ = client.get(f"/speak/projects/{project_id}/economics").json()
    assert econ["split_applies"] is True
    assert econ["inference_margin"] == "0.10"

    # 3. Invite two interviewees who independently attest the same claim.
    iv1 = _invite_and_attest(client, project_id, "a@x.com", "He ran the village bakery for thirty years.")
    _invite_and_attest(client, project_id, "b@x.com", "He ran the village bakery for thirty years.")

    # 4. Invite token resolves (the landing flow).
    invites = client.get(f"/speak/projects/{project_id}/invites").json()
    assert invites["count"] == 2

    # 5. A voice-note answer ingests (hermetic embedding stub).
    r = client.post(f"/speak/interviews/{iv1}/answers",
                    json={"question_id": "q1", "transcript": "He baked bread before dawn every day."})
    assert r.status_code == 201, r.text
    assert r.json()["document_id"]

    # 6. Corroborate → the shared claim is multiply-attested.
    clusters = client.post(f"/speak/projects/{project_id}/corroborate").json()["clusters"]
    attested = [c for c in clusters if c["label"] == "multiply_attested"]
    assert attested
    # The endpoint must carry the actual remembered statement (canonical_text),
    # not just the machine label — the "what everyone agrees on" view renders it
    # (SPR-08 sharpen: the field was omitted, so the surface fell back to the label).
    assert all(c.get("canonical_text") for c in attested)

    # 7. Subject consent (deceased → documented rule).
    r = client.post(f"/speak/projects/{project_id}/subject-consent", json={
        "subject_ref": "the-dad", "subject_status": "deceased",
        "consent_granted": False, "rationale": "deceased 2019; documented rule.",
    })
    assert r.status_code == 200

    # 8. Map an interviewee to a payee.
    r = client.post(f"/speak/projects/{project_id}/contributors",
                    json={"interview_id": iv1, "display_name": "A"})
    assert r.status_code == 201

    # 9. Draft (public) — the corroborated claim is included, none excluded.
    draft = client.post(
        f"/speak/projects/{project_id}/draft",
        headers={"Idempotency-Key": "full-journey-draft"},
        json={"public": True},
    ).json()
    assert "bakery" in draft["prose_text"]
    assert draft["excluded_claim_ids"] == []

    # 10. Publish (gate closed via env) → served as platform_authored, split accrues.
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    r = client.post(f"/speak/projects/{project_id}/publish", json={"ad_revenue_usd": "100"})
    assert r.status_code == 201, r.text
    pub = r.json()
    assert pub["served"] is True
    assert pub["servability"] == "platform_authored"
    assert len(pub["accrual_lines"]) >= 1

    # 11. Physical-book quote — split economics persist, never fulfilled.
    r = client.post(f"/speak/projects/{project_id}/book-orders",
                    json={"book_format": "paperback", "page_count": 200})
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["payer"] == "split"
    assert order["fulfilled"] is False


def _all_events() -> list[dict]:
    events_dir = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    rows: list[dict] = []
    for path in events_dir.rglob("*.jsonl"):
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    return rows


def _speak_to_write_events() -> list[dict]:
    return [
        row for row in _all_events() if row["action_type"] == "seam.speak_to_write"
    ]


def _private_project_with_claim(client: TestClient) -> tuple[str, str]:
    project_id = client.post(
        "/speak/projects", json={"title": "Private memories"}
    ).json()["project_id"]
    interview_id = _invite_and_attest(
        client, project_id, "memory@example.com", "She built the town library."
    )
    return project_id, interview_id


def test_draft_command_converges_blocks_events_and_thread(client):
    project_id, interview_id = _private_project_with_claim(client)
    path = f"/speak/projects/{project_id}/draft"
    headers = {"Idempotency-Key": "draft-command-1"}

    first = client.post(path, headers=headers, json={"public": False})
    second = client.post(path, headers=headers, json={"public": False})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone()[0] == 1
        row = con.execute(
            "SELECT source_block_id, node_id, content FROM outline_blocks"
        ).fetchone()
    claim_id = row[0]
    assert row[1] is None
    assert row[2] == "She built the town library."
    events = _speak_to_write_events()
    assert len(events) == 1
    assert events[0]["payload"] == {
        "action_type": "seam.speak_to_write",
        "from_workflow": "speak",
        "to_workflow": "write",
        "entity_id": claim_id,
        "entity_kind": "speak_claim",
        "provenance_ref": claim_id,
        "terminates": True,
        "contributor_interview_ids": [interview_id],
    }
    assert "library" not in json.dumps(events[0]["payload"])
    thread = client.get(f"/thread/{claim_id}")
    assert thread.status_code == 200
    assert [hop["workflow"] for hop in thread.json()["hops"]] == ["speak", "write"]


def test_draft_command_repairs_append_failure_without_duplicate_draft(client, monkeypatch):
    project_id, _ = _private_project_with_claim(client)
    original = speak_routes.append_event_once
    calls = 0

    def fail_once(event):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("lost event append")
        return original(event)

    monkeypatch.setattr(speak_routes, "append_event_once", fail_once)
    def request():
        return client.post(
            f"/speak/projects/{project_id}/draft",
            headers={"Idempotency-Key": "repair-draft"},
            json={"public": False},
        )
    with pytest.raises(OSError, match="lost event append"):
        request()
    repaired = request()
    assert repaired.status_code == 200
    with duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM outline_blocks").fetchone()[0] == 1
    assert len(_speak_to_write_events()) == 1


def test_partial_event_pair_never_leaves_placement_without_seam(client, monkeypatch):
    project_id, _ = _private_project_with_claim(client)
    original = speak_routes.append_event_once
    calls = 0

    def fail_second(event):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("lost placement append")
        return original(event)

    monkeypatch.setattr(speak_routes, "append_event_once", fail_second)
    path = f"/speak/projects/{project_id}/draft"
    headers = {"Idempotency-Key": "partial-pair-draft"}
    with pytest.raises(OSError, match="lost placement append"):
        client.post(path, headers=headers, json={"public": False})
    assert len(_speak_to_write_events()) == 1
    assert not any(
        event["action_type"] == "outline_block.placed" for event in _all_events()
    )
    repaired = client.post(path, headers=headers, json={"public": False})
    assert repaired.status_code == 200
    assert len(_speak_to_write_events()) == 1
    assert sum(
        event["action_type"] == "outline_block.placed" for event in _all_events()
    ) == 1


def test_draft_command_rolls_back_composition_before_receipt(client, monkeypatch):
    project_id, _ = _private_project_with_claim(client)
    original = speak_routes.biography.generate_draft
    monkeypatch.setattr(
        speak_routes.biography,
        "generate_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("draft fault")),
    )
    path = f"/speak/projects/{project_id}/draft"
    headers = {"Idempotency-Key": "transactional-draft"}
    with pytest.raises(RuntimeError, match="draft fault"):
        client.post(path, headers=headers, json={"public": False})
    with duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM outline_blocks").fetchone()[0] == 0
    assert not any(
        event["action_type"] == "outline_block.placed" for event in _all_events()
    )

    monkeypatch.setattr(speak_routes.biography, "generate_draft", original)
    repaired = client.post(path, headers=headers, json={"public": False})
    assert repaired.status_code == 200
    with duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone()[0] == 1
    assert sum(
        event["action_type"] == "outline_block.placed" for event in _all_events()
    ) == 1


def test_draft_emits_exactly_one_reference_event_per_placed_claim(client):
    project_id, interview_id = _private_project_with_claim(client)
    second = client.post(
        f"/speak/interviews/{interview_id}/claims",
        json={"text": "She also funded the reading room."},
    )
    assert second.status_code == 201
    result = client.post(
        f"/speak/projects/{project_id}/draft",
        headers={"Idempotency-Key": "two-claim-draft"},
        json={"public": False},
    )
    assert result.status_code == 200
    with duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True) as con:
        claim_ids = {
            row[0]
            for row in con.execute(
                "SELECT source_block_id FROM outline_blocks "
                "WHERE source_block_kind = 'speak_claim'"
            ).fetchall()
        }
    events = _speak_to_write_events()
    assert len(events) == len(claim_ids) == 2
    assert {event["payload"]["entity_id"] for event in events} == claim_ids
    assert all("text" not in event["payload"] for event in events)


def test_draft_command_refuses_reuse_and_disabled_events_before_mutation(client, monkeypatch):
    project_id, _ = _private_project_with_claim(client)
    path = f"/speak/projects/{project_id}/draft"
    headers = {"Idempotency-Key": "fixed-draft"}
    assert client.post(path, headers=headers, json={"public": False}).status_code == 200
    assert client.post(path, headers=headers, json={"public": True}).status_code == 409

    other_project, _ = _private_project_with_claim(client)
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "true")
    with pytest.raises(RuntimeError, match="event persistence is disabled"):
        client.post(
            f"/speak/projects/{other_project}/draft",
            headers={"Idempotency-Key": "disabled-draft"},
            json={"public": False},
        )
    with duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True) as con:
        assert con.execute(
            "SELECT count(*) FROM deliverables WHERE title = 'Biography'"
        ).fetchone()[0] == 1


# ── SPR-11 — the biography TEMPLATE composition, end-to-end ──────────────


def test_biography_template_composes_three_surfaces_over_one_graph(client):
    """SPR-11 M2 — "start a biography" provisions Research + Write + Speak
    over the ONE graph, all wired to the same investigation identity. The
    Write deliverable's research link == the investigation_id; the Speak
    interview project is created and linked via the shared composition."""
    # 1. The Research folder — created the normal way (POST /investigations).
    r = client.post("/investigations", json={"question": "The life of Grandma."})
    assert r.status_code == 202, r.text  # accepted; orchestrator runs async
    investigation_id = r.json()["investigation_id"]

    # 2. Compose the biography template on that Research folder.
    r = client.post("/speak/biography", json={
        "investigation_id": investigation_id, "subject_name": "Grandma",
    })
    assert r.status_code == 201, r.text
    comp = r.json()
    assert comp["investigation_id"] == investigation_id
    assert comp["deliverable_id"] and comp["project_id"]

    # 3. Write resolves to the SAME identity: the deliverable's research link
    #    is the biography's investigation_id (not a second, orphan identity).
    dlv = client.get(f"/deliverables/{comp['deliverable_id']}").json()
    assert dlv["investigation_root_id"] == investigation_id

    # 4. The Speak interview project is the shipped one — it appears in the
    #    project index and accepts invites (the M3 talk flow).
    projects = client.get("/speak/projects").json()["projects"]
    assert any(p["project_id"] == comp["project_id"] for p in projects)


def test_biography_invite_lands_on_talk_flow_for_that_project(client):
    """SPR-11 M3 — an invite into the biography's Speak project drops the
    recipient onto the talk-flow landing for THAT project (the captured
    memory feeds the biography's shared graph, not a side store). Reuses the
    shipped invite + token-landing flow (SPR-10)."""
    investigation_id = client.post(
        "/investigations", json={"question": "The life of Dad."}
    ).json()["investigation_id"]
    comp = client.post("/speak/biography", json={
        "investigation_id": investigation_id, "subject_name": "Dad",
    }).json()

    # Invite a friend into the biography's Speak project.
    iv = client.post(
        f"/speak/projects/{comp['project_id']}/invites",
        json={"informant_handle": "a friend"},
    ).json()
    token = iv["link"].split("token=")[1]

    # The invitee's token lands on the talk flow for THIS biography's project.
    landing = client.get(f"/speak/invite/{token}").json()
    assert landing["project_id"] == comp["project_id"]


# ── gate refusals (the load-bearing ones) ───────────────────────────────


def test_publish_refused_when_legal_gate_open(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    r = client.post("/speak/projects", json={
        "title": "Bio", "subject_ref": "x", "subject_status": "deceased",
        "publish_intent": "will_be_public",
    })
    project_id = r.json()["project_id"]
    client.post(f"/speak/projects/{project_id}/subject-consent", json={
        "subject_ref": "x", "subject_status": "deceased",
        "consent_granted": False, "rationale": "documented.",
    })
    r = client.post(f"/speak/projects/{project_id}/publish", json={})
    assert r.status_code == 409
    assert "legal gate" in r.json()["detail"] or "G2" in r.json()["detail"]


def test_open_public_refused_without_g7(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", raising=False)
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    r = client.post(f"/speak/projects/{pid}/open-public")
    assert r.status_code == 403


def test_answer_before_consent_refused(client):
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    r = client.post(f"/speak/interviews/{iv['interview_id']}/answers",
                    json={"question_id": "q1", "transcript": "answer before consent"})
    assert r.status_code == 403


def test_resolve_unknown_token_404(client):
    r = client.get("/speak/invites/resolve", params={"token": "nope"})
    assert r.status_code == 404


def test_private_publish_not_served(client):
    pid = client.post("/speak/projects", json={
        "title": "Private bio", "publish_intent": "private_never_published",
    }).json()["project_id"]
    r = client.post(f"/speak/projects/{pid}/publish", json={})
    assert r.status_code == 201, r.text
    assert r.json()["served"] is False
    assert r.json()["visibility"] == "private"


def _token_from_link(link: str) -> str:
    return link.split("token=", 1)[1]


def test_invitee_token_flow(client):
    # Operator creates a will-be-public project + invites someone.
    project_id = client.post("/speak/projects", json={
        "title": "Dad's biography", "subject_ref": "the-dad",
        "subject_status": "deceased", "publish_intent": "will_be_public",
    }).json()["project_id"]
    iv = client.post(f"/speak/projects/{project_id}/invites",
                     json={"informant_email": "aunt@x.com"}).json()
    token = _token_from_link(iv["link"])

    # The invitee lands via their TOKEN (no operator account).
    landing = client.get(f"/speak/invite/{token}").json()
    assert landing["project_title"] == "Dad's biography"
    assert "publish" in landing["required_consent_scopes"]
    assert landing["granted_consent_scopes"] == []  # nothing granted yet

    # They grant scoped consent (record only — declining publish is allowed).
    r = client.post(f"/speak/invite/{token}/consent", json={"scopes": ["record"]})
    assert r.status_code == 200
    assert "record" in r.json()["granted"]

    # Now they can answer; the text they submit is the (corrected) transcript.
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": "He taught me to bake bread before dawn."})
    assert r.status_code == 201, r.text

    # The landing reflects their contribution.
    landing2 = client.get(f"/speak/invite/{token}").json()
    assert "record" in landing2["granted_consent_scopes"]
    assert any("bread" in t["text"] for t in landing2["transcript"])


def test_invitee_answer_requires_consent(client):
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    token = _token_from_link(iv["link"])
    # Answer before consent → 403 (ConsentRequired surfaced).
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": "before consent"})
    assert r.status_code == 403


def test_invitee_bad_token_404(client):
    assert client.get("/speak/invite/not-a-real-token").status_code == 404
    assert client.post("/speak/invite/not-a-real-token/consent",
                       json={"scopes": ["record"]}).status_code == 404
    assert client.post("/speak/invite/not-a-real-token/answer",
                       json={"question_id": "q", "transcript": "x"}).status_code == 404


def test_invitee_surface_open_while_operator_endpoints_authed(client, monkeypatch):
    # Turn operator auth ON. The operator surface must require auth; the
    # token-gated invitee surface must still be REACHABLE (token is the
    # credential), returning 404 for a bad token rather than an auth 401.
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")
    operator_resp = client.get("/speak/projects")
    assert operator_resp.status_code in (401, 403), "operator endpoint must be auth-gated"
    invitee_resp = client.get("/speak/invite/some-token")
    assert invitee_resp.status_code not in (401, 403), "invitee surface must be open (token-gated)"
    assert invitee_resp.status_code == 404  # reached the endpoint; token invalid


def test_invitee_decline(client):
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    token = _token_from_link(iv["link"])
    r = client.post(f"/speak/invite/{token}/decline")
    assert r.status_code == 200
    assert r.json()["status"] == "declined"


def test_list_projects(client):
    # Fresh DB → empty list.
    r = client.get("/speak/projects")
    assert r.status_code == 200
    assert r.json()["count"] == 0
    # Create two → both listed with their publish intent + interview count.
    client.post("/speak/projects", json={"title": "Dad's biography"})
    client.post("/speak/projects", json={"title": "Mom's biography", "publish_intent": "will_be_public"})
    data = client.get("/speak/projects").json()
    assert data["count"] == 2
    titles = {p["title"] for p in data["projects"]}
    assert titles == {"Dad's biography", "Mom's biography"}
    assert all("interview_count" in p and "publish_intent" in p for p in data["projects"])


# ── SPR-10 M1: public feed split ──────────────────────────────────────────


def test_public_feed_shows_only_public_projects(client):
    # Fresh → empty feed (honest empty).
    r = client.get("/speak/feed")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "projects": []}
    # One private, one public → only the public one is in the feed.
    client.post("/speak/projects", json={"title": "Private one"})
    client.post("/speak/projects", json={"title": "Public one", "publish_intent": "will_be_public"})
    feed = client.get("/speak/feed").json()
    assert feed["count"] == 1
    assert feed["projects"][0]["title"] == "Public one"
    # The operator dashboard (/projects) still shows BOTH.
    assert client.get("/speak/projects").json()["count"] == 2


# ── SPR-10 M2: economics READS gate status, shows gated (never closes) ─────


def test_economics_surfaces_gate_status_gated_by_default(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.delenv("ANTIEK_STRIPE_PROVIDER", raising=False)
    pid = client.post("/speak/projects",
                      json={"title": "Bio", "publish_intent": "will_be_public"}).json()["project_id"]
    ec = client.get(f"/speak/projects/{pid}/economics").json()
    # Public ⇒ split applies (the binding rule).
    assert ec["split_applies"] is True
    # The gate state is SHOWN as gated/not-activated — read-only, deny-by-default.
    assert ec["public_publishing_allowed"] is False
    assert ec["disbursement_allowed"] is False
    assert "legal gate" in ec["public_publishing_reason"]


# ── SPR-10 M3: AI-grade an interview + release routes to escrow ────────────


def test_grade_interview_endpoint_scores_and_keeps(client):
    pid = client.post("/speak/projects",
                      json={"title": "Bio", "publish_intent": "will_be_public"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    interview_id = iv["interview_id"]
    client.post(f"/speak/interviews/{interview_id}/consent", json={"scopes": ["record"]})
    client.post(f"/speak/interviews/{interview_id}/answers", json={
        "question_id": "q1",
        "transcript": "He ran the village bakery for thirty years through the war years, "
                      "baking before dawn and feeding the whole street when flour was scarce.",
    })
    r = client.post(f"/speak/interviews/{interview_id}/grade", json={
        "information_goal": "his work and the war years",
        "must_cover": ["the bakery", "the war years"],
        "budget_usd": "100", "per_interview_cap_usd": "40",
    })
    assert r.status_code == 201, r.text
    g = r.json()
    assert 0.0 <= g["score"] <= 1.0
    assert g["graded_by"] == "deterministic-rubric"  # no dispatch_fn on this route
    assert "passed" in g and "honest" in g and "gamed_risk" in g


def test_release_payout_accrues_to_escrow_no_disbursement(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_STRIPE_PROVIDER", raising=False)  # disbursement gated
    pid = client.post("/speak/projects",
                      json={"title": "Bio", "publish_intent": "will_be_public"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    interview_id = iv["interview_id"]
    client.post(f"/speak/interviews/{interview_id}/consent", json={"scopes": ["record", "attribute"]})
    client.post(f"/speak/interviews/{interview_id}/answers", json={
        "question_id": "q1",
        "transcript": "He ran the village bakery for thirty years through the war years daily.",
    })
    client.post(f"/speak/interviews/{interview_id}/claims",
                json={"text": "He ran the bakery during the war.", "confidence": 0.9})
    client.post(f"/speak/projects/{pid}/contributors",
                json={"interview_id": interview_id, "display_name": "A"})
    client.post(f"/speak/interviews/{interview_id}/grade",
                json={"information_goal": "the bakery and the war", "must_cover": ["bakery", "war"]})
    r = client.post(f"/speak/projects/{pid}/release-payout", json={
        "information_goal": "the bakery and the war", "ad_revenue_usd": "100",
        "budget_usd": "1000", "per_interview_cap_usd": "0",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    # Routed via §9: accrual lines exist with share fractions (not a flat fee).
    assert any(l["interview_id"] == interview_id for l in body["accrual_lines"])
    # spent accrued to escrow (a real dollar figure because ad_revenue>0).
    assert "spent_usd" in body
