"""Honest multi-signal public ranking (NOT ML)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.speak import pushes as speak_pushes


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-rank-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_tokenize_interest_drops_stopwords():
    toks = speak_pushes.tokenize_interest("Uncle Theo bakery")
    assert toks == {"uncle", "theo", "bakery"}
    assert "the" not in speak_pushes.tokenize_interest("the story of life")


def test_combine_scores_weights_and_interest_path():
    base = speak_pushes._combine_scores(
        voice_need=1.0, recency=1.0, specificity=1.0, overlap=0.0, has_interest=False
    )
    assert abs(base - 1.0) < 1e-9
    with_interest = speak_pushes._combine_scores(
        voice_need=1.0, recency=1.0, specificity=1.0, overlap=1.0, has_interest=True
    )
    assert abs(with_interest - 1.0) < 1e-9
    no_overlap = speak_pushes._combine_scores(
        voice_need=1.0, recency=1.0, specificity=1.0, overlap=0.0, has_interest=True
    )
    assert no_overlap < with_interest
    assert speak_pushes._voice_need_score(0) > speak_pushes._voice_need_score(5)


def test_specificity_and_overlap_helpers():
    assert speak_pushes._specificity_score("Uncle Theo Bakery Memoir", "Theo") > 0.3
    assert speak_pushes._specificity_score("a", None) == 0.0
    ov = speak_pushes._overlap_score(
        "Uncle Theo Bakery", "Theo", "bakery uncle"
    )
    assert ov > 0
    assert speak_pushes._overlap_score("Garden", "May", "bakery") == 0.0


def test_api_few_voices_outrank_many_and_honesty_id(client):
    need = client.post(
        "/speak/projects",
        json={
            "title": "Uncle Theo Bakery Memoir",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    crowded = client.post(
        "/speak/projects",
        json={
            "title": "Uncle Theo Bakery Memoir Two",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    for i in range(4):
        r = client.post(
            f"/speak/projects/{crowded['project_id']}/invites",
            json={"informant_email": f"v{i}@x.com"},
        )
        assert r.status_code == 201, r.text

    opps = client.get("/speak/opportunities").json()
    assert opps["honesty"]["ranking"] == speak_pushes.RANKING_HONESTY_ID
    assert "not_ml" in opps["honesty"]["ranking"]
    ids = [o["project_id"] for o in opps["public_opportunities"]]
    assert ids.index(need["project_id"]) < ids.index(crowded["project_id"])
    top = opps["public_opportunities"][0]
    assert top["project_id"] == need["project_id"]
    assert isinstance(top["rank_score"], float)
    assert "needs voices" in top["rank_reason"]
    assert "not ML" in top["rank_reason"]

    pushes = client.get("/speak/pushes").json()
    assert pushes["honesty"]["public_ranking"] == speak_pushes.RANKING_HONESTY_ID


def test_api_interest_query_boosts_title_match(client):
    bakery = client.post(
        "/speak/projects",
        json={
            "title": "Uncle Theo Bakery Days",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    garden = client.post(
        "/speak/projects",
        json={
            "title": "Aunt May Garden Notes",
            "subject_ref": "Aunt May",
            "publish_intent": "will_be_public",
        },
    ).json()
    interested = client.get(
        "/speak/opportunities", params={"interest": "bakery theo"}
    ).json()
    ids = [o["project_id"] for o in interested["public_opportunities"]]
    assert ids[0] == bakery["project_id"]
    assert bakery["project_id"] in ids and garden["project_id"] in ids
    top = interested["public_opportunities"][0]
    assert "overlap" in top["rank_reason"]
