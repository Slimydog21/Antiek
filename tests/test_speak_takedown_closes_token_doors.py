"""A takedown closes invite-token doors minted BEFORE it, not only new ones.

``mint_open_contribution`` refuses a project under active takedown, but a
stranger who minted an open-contribution token earlier kept a live door:
``GET /speak/invite/{token}`` is unauthenticated and returns
``subject_ref``, and the token's write routes kept accepting consent and
answers, while ``/speak/feed`` and ``/speak/opportunities`` already hid the
project. Every token route resolves through ``invitations.resolve_token``,
so the takedown is enforced there, and the operator re-ping surface (which
hands the same door out by email) consults the same predicate.

Scope, pinned by the control assertions below:
  * an open-contribution token closes under ANY active takedown on its
    project — the same predicate that hides the project from the public
    lists, because an anonymous mint proves nothing about who holds it;
  * any token closes when its own interview is the takedown target;
  * an operator-minted family invite is NOT closed by a takedown aimed at
    something else in the project (that is a product decision, recorded
    in the fix's decision note, not made here).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import speak_routes
from interfaces.research.api.app import create_app
from interfaces.research.api.auth import reset_auth_throttles
from runtime.db_lock import connect_write
from substrate.speak import async_interview, invitations, pushes, takedown


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


class _StubTranscriber:
    def transcribe(self, audio: bytes, **_: object) -> str:
        return "a transcript that must never land"


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch) -> str:
    tmpdir = tempfile.mkdtemp(prefix="speak-takedown-doors-")
    path = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_SPEAK_REPING_EMAIL", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    return path


@pytest.fixture
def client(db_path: str) -> Iterator[TestClient]:
    reset_auth_throttles()
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app) as c:
        yield c
    reset_auth_throttles()


def _public_project(client: TestClient, subject: str) -> str:
    r = client.post("/speak/projects", json={
        "title": f"Biography of {subject}", "subject_ref": subject,
        "subject_status": "deceased", "publish_intent": "will_be_public",
    })
    assert r.status_code == 201, r.text
    return str(r.json()["project_id"])


def _open_token(client: TestClient, pid: str) -> str:
    r = client.post(f"/speak/projects/{pid}/open-contribute")
    assert r.status_code == 201, r.text
    return str(r.json()["token"])


def _take_down(client: TestClient, pid: str, kind: str, target: str) -> str:
    r = client.post(f"/speak/projects/{pid}/takedowns", json={
        "target_kind": kind, "target_id": target,
        "requested_by": "the subject", "reason": "withdrew",
    })
    assert r.status_code == 201, r.text
    return str(r.json()["takedown_id"])


def _door_statuses(client: TestClient, token: str) -> dict[str, tuple[int, str]]:
    """Hit every token-keyed door; return (status, body) per door."""
    base = f"/speak/invite/{token}"
    calls = {
        "landing": lambda: client.get(base),
        "resolve": lambda: client.get("/speak/invites/resolve", params={"token": token}),
        "consent": lambda: client.post(f"{base}/consent", json={"scopes": ["record"]}),
        "answer": lambda: client.post(f"{base}/answer", json={
            "question_id": "q1", "transcript": "late words about the subject",
        }),
        "voice": lambda: client.post(
            f"{base}/voice", params={"question_id": "q1"}, content=b"audio",
            headers={"content-type": "audio/webm"},
        ),
        "followups": lambda: client.post(f"{base}/followups"),
        "decline": lambda: client.post(f"{base}/decline"),
    }
    out = {}
    for name, call in calls.items():
        r = call()
        out[name] = (r.status_code, r.text)
    return out


def test_takedown_closes_every_door_of_a_previously_minted_open_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", _StubTranscriber())
    subject = "jane.doe@example.test"
    pid = _public_project(client, subject)
    token = _open_token(client, pid)
    before = client.get(f"/speak/invite/{token}")
    assert before.status_code == 200 and before.json()["subject_ref"] == subject

    _take_down(client, pid, "subject", subject)

    statuses = _door_statuses(client, token)
    leaked = {k: v for k, v in statuses.items() if v[0] != 404}
    assert not leaked, f"open-contribution token still live after takedown: {leaked}"
    assert all(subject not in body for _, body in statuses.values())


@pytest.mark.parametrize("kind", ["claim", "interview"])
def test_any_takedown_kind_closes_open_tokens_on_the_project(
    client: TestClient, kind: str,
) -> None:
    """The public lists hide a project under ANY active takedown; an
    anonymously minted door follows the same predicate, whatever the
    target kind."""
    pid = _public_project(client, "the-dad")
    token = _open_token(client, pid)
    _take_down(client, pid, kind, "some-other-target")
    assert client.get(f"/speak/invite/{token}").status_code == 404


def test_reversal_reopens_the_open_token_with_its_project(
    client: TestClient, db_path: str,
) -> None:
    """Closing is a predicate over active takedowns, not a destructive
    delete: once the project is back on the public lists, the door the
    public lists would mint anyway is live again, and a control project's
    token was never touched."""
    pid = _public_project(client, "the-dad")
    control = _public_project(client, "bob.control@example.test")
    token = _open_token(client, pid)
    control_token = _open_token(client, control)
    tid = _take_down(client, pid, "subject", "the-dad")
    assert client.get(f"/speak/invite/{token}").status_code == 404
    assert client.get(f"/speak/invite/{control_token}").status_code == 200

    with connect_write(db_path, purpose="test:reverse") as con:
        takedown.reverse_takedown(con, takedown_id=tid)
    assert client.get(f"/speak/invite/{token}").status_code == 200


def test_interview_takedown_closes_that_interviews_operator_invite(
    client: TestClient,
) -> None:
    """Nearest sibling: an operator-minted family invite whose OWN interview
    is taken down. The landing replays the transcript, and the write doors
    would keep adding statements to an interview under takedown."""
    pid = _public_project(client, "the-dad")
    r = client.post(f"/speak/projects/{pid}/invites",
                    json={"informant_email": "aunt@example.test"})
    assert r.status_code == 201, r.text
    token, interview_id = r.json()["token"], r.json()["interview_id"]
    other = client.post(f"/speak/projects/{pid}/invites",
                        json={"informant_email": "cousin@example.test"}).json()

    _take_down(client, pid, "interview", interview_id)

    statuses = _door_statuses(client, token)
    leaked = {k: v for k, v in statuses.items() if v[0] != 404}
    assert not leaked, f"invite for a taken-down interview still live: {leaked}"
    # Control: a sibling family invite on the same project is untouched.
    assert client.get(f"/speak/invite/{other['token']}").status_code == 200


def test_operator_invite_survives_takedown_aimed_elsewhere(client: TestClient) -> None:
    """Pins the scope of this fix: a claim/subject takedown does not close a
    family invite the operator handed out (policy left to the operator)."""
    pid = _public_project(client, "the-dad")
    fam = client.post(f"/speak/projects/{pid}/invites",
                      json={"informant_email": "aunt@example.test"}).json()
    _take_down(client, pid, "claim", "claim-x")
    assert client.get(f"/speak/invite/{fam['token']}").status_code == 200


def test_resolve_token_is_the_closed_door_for_substrate_callers(db_path: str) -> None:
    """The enforcement lives in ``resolve_token`` itself, so a substrate
    caller that is not one of the routes gets the same closed door."""
    from substrate.graph.schema import init_database
    from substrate.speak import project

    with connect_write(db_path, purpose="test:setup") as con:
        init_database(con)
        pid = project.create_project(
            con, title="t", subject_ref="the-dad", subject_status="deceased",
            publish_intent="will_be_public",
        ).project_id
        inv = invitations.mint_open_contribution(con, pid)
        assert invitations.resolve_token(con, inv.token) is not None
        takedown.request_takedown(
            con, project_id=pid, target_kind="subject", target_id="the-dad",
        )
        assert invitations.resolve_token(con, inv.token) is None


def test_reping_never_hands_out_a_closed_door(client: TestClient, db_path: str) -> None:
    """The operator re-ping surface lists and (optionally) emails the same
    ``/speak/invite/{token}`` door. A closed door is neither listed nor
    re-pinged."""
    pid = _public_project(client, "the-dad")
    token = _open_token(client, pid)
    fam = client.post(f"/speak/projects/{pid}/invites",
                      json={"informant_email": "aunt@example.test"}).json()
    listed = {p.token for p in pushes.list_private_repings_at(db_path)}
    assert {token, fam["token"]} <= listed

    _take_down(client, pid, "interview", fam["interview_id"])

    listed = {p.token for p in pushes.list_private_repings_at(db_path)}
    assert token not in listed and fam["token"] not in listed, listed

    # A declined invitee under takedown must not get its closed token
    # echoed back by the declined branch either.
    async_interview.decline(db_path, fam["interview_id"])
    with connect_write(db_path, purpose="test:lookup") as con:
        rows = invitations.lifecycle(con, pid)
    assert len(rows) == 2
    for row in rows:
        res = pushes.prepare_reping(db_path, interview_id=row["interview_id"],
                                    send_email=True)
        assert res.invite_path == "" and res.token == "", res
        assert res.followups_added == 0
        assert res.skipped_reason and "takedown" in res.skipped_reason


# ---------------------------------------------------------------------------
# Race: a takedown that lands AFTER a write route checked the token but
# BEFORE its write. The routes resolve the token under one lock and then call
# submit_answer / next_followups, which take their own sequential locks (and
# the voice route transcribes for seconds in between), so the route's check
# alone leaves a window in which a closed door still writes.
# ---------------------------------------------------------------------------


def _turns(db_path: str, interview_id: str, role: str) -> list[dict[str, object]]:
    import json

    with connect_write(db_path, purpose="test:turns") as con:
        row = con.execute(
            "SELECT transcript_turns FROM interviews WHERE interview_id = ?",
            [interview_id],
        ).fetchone()
    return [t for t in json.loads(row[0] or "[]") if t.get("role") == role]


def _documents_mentioning(db_path: str, needle: str) -> int:
    with connect_write(db_path, purpose="test:docs") as con:
        row = con.execute(
            "SELECT count(*) FROM documents WHERE raw_text LIKE ?", [f"%{needle}%"],
        ).fetchone()
    return int(row[0])


def _consented_open_token(client: TestClient, subject: str) -> tuple[str, str, str]:
    pid = _public_project(client, subject)
    token = _open_token(client, pid)
    r = client.post(f"/speak/invite/{token}/consent", json={"scopes": ["record"]})
    assert r.status_code == 200, r.text
    return pid, token, str(r.json()["interview_id"])


def _take_down_now(db_path: str, pid: str, subject: str) -> None:
    with connect_write(db_path, purpose="test:race-takedown") as con:
        takedown.request_takedown(
            con, project_id=pid, target_kind="subject", target_id=subject,
        )


def test_takedown_during_voice_transcription_refuses_the_answer(
    client: TestClient, db_path: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The widest window: the voice route checks the token, then spends
    seconds in Whisper before it writes. A takedown landing there must still
    keep the answer out of the interview and out of the substrate."""
    subject = "the-dad"
    pid, token, interview_id = _consented_open_token(client, subject)
    spoken = "race words spoken while the takedown landed"

    class _TakedownMidTranscription:
        def transcribe(self, audio: bytes, **_: object) -> str:
            _take_down_now(db_path, pid, subject)
            return spoken

    monkeypatch.setattr(speak_routes, "_INVITEE_TRANSCRIBER", _TakedownMidTranscription())
    r = client.post(
        f"/speak/invite/{token}/voice", params={"question_id": "q1"},
        content=b"audio", headers={"content-type": "audio/webm"},
    )
    assert r.status_code == 404, r.text
    assert subject not in r.text and spoken not in r.text
    assert _turns(db_path, interview_id, "informant") == []
    assert _documents_mentioning(db_path, spoken) == 0


def test_takedown_between_token_check_and_answer_write_refuses_it(
    client: TestClient, db_path: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = "the-dad"
    pid, token, interview_id = _consented_open_token(client, subject)
    real_submit = speak_routes.submit_answer

    def _takedown_then_submit(*args: Any, **kwargs: Any) -> Any:
        _take_down_now(db_path, pid, subject)
        return real_submit(*args, **kwargs)

    monkeypatch.setattr(speak_routes, "submit_answer", _takedown_then_submit)
    typed = "typed words racing the takedown"
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": typed})
    assert r.status_code == 404, r.text
    assert _turns(db_path, interview_id, "informant") == []
    assert _documents_mentioning(db_path, typed) == 0


def test_takedown_between_token_check_and_followups_persists_nothing(
    client: TestClient, db_path: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = "the-dad"
    pid, token, interview_id = _consented_open_token(client, subject)
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": "an earlier memory"})
    assert r.status_code == 201, r.text
    real_next = speak_routes.next_followups

    def _takedown_then_followups(*args: Any, **kwargs: Any) -> Any:
        _take_down_now(db_path, pid, subject)
        return real_next(*args, **kwargs)

    monkeypatch.setattr(speak_routes, "next_followups", _takedown_then_followups)
    r = client.post(f"/speak/invite/{token}/followups")
    assert r.status_code == 404, r.text
    assert "followups" not in r.json()
    assert _turns(db_path, interview_id, "interviewer") == []


def test_takedown_during_reping_generation_sends_no_door(
    client: TestClient, db_path: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator re-ping: its gate passes, then a takedown lands while the
    followups are generated. The result must not hand out the closed door
    (and so never emails it)."""
    subject = "the-dad"
    pid, token, interview_id = _consented_open_token(client, subject)
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": "an earlier memory"})
    assert r.status_code == 201, r.text
    real_next = async_interview.next_followups

    def _takedown_then_followups(*args: Any, **kwargs: Any) -> Any:
        _take_down_now(db_path, pid, subject)
        return real_next(*args, **kwargs)

    monkeypatch.setattr(async_interview, "next_followups", _takedown_then_followups)
    res = pushes.prepare_reping(db_path, interview_id=interview_id, send_email=True)
    assert res.token == "" and res.invite_path == "", res
    assert res.email_status == "skipped_takedown", res
    assert _turns(db_path, interview_id, "interviewer") == []


def test_door_guard_holds_inside_the_substrate_write(db_path: str) -> None:
    """The guard lives in async_interview itself, so a caller that passes the
    invite token gets the takedown enforced under the same lock as the write,
    whoever checked the token earlier. A token only vouches for its own
    interview."""
    from substrate.graph.schema import init_database
    from substrate.speak import consent, project
    from substrate.speak.consent import ConsentScope

    with connect_write(db_path, purpose="test:setup") as con:
        init_database(con)
        pid = project.create_project(
            con, title="t", subject_ref="the-dad", subject_status="deceased",
            publish_intent="will_be_public",
        ).project_id
        other_pid = project.create_project(
            con, title="o", subject_ref="someone-else", subject_status="deceased",
            publish_intent="will_be_public",
        ).project_id
        inv = invitations.mint_open_contribution(con, pid)
        other = invitations.mint_open_contribution(con, other_pid)
        consent.record_consent(con, interview_id=inv.interview_id,
                               scopes=[ConsentScope.RECORD])

    # A token for a different, still-open interview never vouches for this one.
    with pytest.raises(invitations.InviteDoorClosed):
        async_interview.submit_answer(
            db_path, interview_id=inv.interview_id, question_id="q1",
            transcript="borrowed door", embedder=StubEmbedding(),
            door_token=other.token,
        )

    with connect_write(db_path, purpose="test:takedown") as con:
        takedown.request_takedown(
            con, project_id=pid, target_kind="subject", target_id="the-dad",
        )
    with pytest.raises(invitations.InviteDoorClosed):
        async_interview.submit_answer(
            db_path, interview_id=inv.interview_id, question_id="q1",
            transcript="words after the takedown", embedder=StubEmbedding(),
            door_token=inv.token,
        )
    with pytest.raises(invitations.InviteDoorClosed):
        async_interview.next_followups(
            db_path, interview_id=inv.interview_id, door_token=inv.token,
        )
    assert _turns(db_path, inv.interview_id, "informant") == []
    assert _documents_mentioning(db_path, "borrowed door") == 0
    assert _documents_mentioning(db_path, "words after the takedown") == 0
