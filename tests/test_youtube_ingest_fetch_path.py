"""YouTube source ingest records which metadata fetch path supplied the row."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from acquisition.youtube.client import TranscriptSegment, reset_youtube_fetch_counter
from interfaces.research.api import research_tool_search
from interfaces.research.api.app import create_app
from runtime.connectors.registry import ToolConnectionUnavailable
from runtime.connectors.youtube import YouTubeVideoMetadata
from runtime.db_lock import connect_read


def test_fetch_path_recorded_differs_with_and_without_credential(
    tmp_path: Path, monkeypatch,
) -> None:
    db_path = tmp_path / "graph.duckdb"
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setattr(
        "acquisition.youtube.client._fetch_metadata",
        lambda _video_id: {
            "title": "yt-dlp title",
            "uploader": "yt-dlp channel",
            "duration": 180,
            "description": "yt-dlp description",
            "upload_date": "20260812",
        },
    )
    segments = [
        TranscriptSegment(
            text="This transcript has enough words for the graph to store its source "
            "and keep the provenance attached to the document row.",
            start_seconds=float(i * 10),
            duration_seconds=10.0,
        )
        for i in range(6)
    ]
    monkeypatch.setattr(
        "acquisition.youtube.client._fetch_transcript",
        lambda _video_id: (segments, "human"),
    )
    reset_youtube_fetch_counter()
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )

    monkeypatch.setattr(
        research_tool_search, "connected_tool_for_request", lambda _request, _vendor: None
    )
    with TestClient(app) as client:
        first = client.post(
            "/sources/ingest",
            json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},
        )
        assert first.status_code == 202
        assert first.json()["status"] == "ingested"

        class FakeConnector:
            closed = False

            def video_metadata(self, video_id: str) -> YouTubeVideoMetadata:
                assert video_id == "bbbbbbbbbbb"
                return YouTubeVideoMetadata(
                    video_id=video_id,
                    title="Data API title",
                    channel_title="Data API channel",
                    description="Data API description",
                    published_at="2026-08-12T00:00:00Z",
                    duration_seconds=192,
                )

            def close(self) -> None:
                self.closed = True

        connector = FakeConnector()
        monkeypatch.setattr(
            research_tool_search,
            "connected_tool_for_request",
            lambda _request, _vendor: connector,
        )
        second = client.post(
            "/sources/ingest",
            json={"url": "https://www.youtube.com/watch?v=bbbbbbbbbbb"},
        )
        assert second.status_code == 202
        assert second.json()["status"] == "ingested"

    with connect_read(str(db_path)) as con:
        rows = con.execute(
            "SELECT document_id, title, metadata FROM documents "
            "WHERE document_id IN (?, ?)",
            ["doc-yt-aaaaaaaaaaa", "doc-yt-bbbbbbbbbbb"],
        ).fetchall()
    documents = {
        document_id: (title, metadata if isinstance(metadata, dict) else json.loads(metadata))
        for document_id, title, metadata in rows
    }
    assert len(documents) == 2
    assert documents["doc-yt-aaaaaaaaaaa"][1]["metadata_source"] == "yt_dlp"
    assert documents["doc-yt-bbbbbbbbbbb"][1]["metadata_source"] == "youtube_data_api"
    assert documents["doc-yt-bbbbbbbbbbb"][0] == "Data API title"
    assert connector.closed


def test_connected_tool_for_request_needs_a_signed_in_owner_and_a_connection(
    monkeypatch,
) -> None:
    sentinel = object()
    calls: list[tuple[str, str]] = []

    def resolve(owner: str, vendor: str) -> object:
        calls.append((owner, vendor))
        return sentinel

    monkeypatch.setattr(research_tool_search, "resolve_tool_connection", resolve)
    request = SimpleNamespace(
        state=SimpleNamespace(user_id="owner-a", auth_method="antiek_session_cookie")
    )
    assert research_tool_search.connected_tool_for_request(request, "youtube") is sentinel
    assert calls == [("owner-a", "youtube")]

    request.state.auth_method = "bearer_token"
    assert research_tool_search.connected_tool_for_request(request, "youtube") is None
    assert calls == [("owner-a", "youtube")]

    request.state.auth_method = "antiek_session_cookie"

    def unavailable(_owner: str, _vendor: str) -> object:
        raise ToolConnectionUnavailable("no connection")

    monkeypatch.setattr(research_tool_search, "resolve_tool_connection", unavailable)
    assert research_tool_search.connected_tool_for_request(request, "youtube") is None
