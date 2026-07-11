from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import (
    PreparedChapterTTSRequest,
    prepare_chapter_tts_request,
    verify_chapter_tts_authorization,
)
from substrate.multimedia.execution_authorization import (
    ExecutionAuthorizationIntegrityError,
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
)
from substrate.multimedia.planner import (
    ChapterPlan,
    MultimediaPlan,
    MultimediaPlanRequest,
)

KEY = b"chapter-tts-authority-key-32-bytes-long"
NOW = datetime(2026, 7, 11, tzinfo=UTC)
CATALOG_DIGEST = "a" * 64
RECOVERY_DIGEST = "b" * 64


def _plan(*, chapters: int = 1) -> MultimediaPlan:
    chapter_rows = tuple(
        ChapterPlan(
            chapter_id=f"chapter-{index}",
            title=f"Chapter {index}",
            minutes=15 / chapters,
            purpose="Explain grounded evidence",
            arc_id=f"arc-{index}",
            source_chunk_ids=(f"chunk-{index}",),
        )
        for index in range(chapters)
    )
    lines = tuple(
        ScriptLine(
            line_id=f"chapter-{index}-line-0",
            sequence=index,
            text=f"Grounded chapter {index} explains the evidence.",
            kind="narration",
        )
        for index in range(chapters)
    )
    return MultimediaPlan(
        request=MultimediaPlanRequest(topic="Aircraft", target_minutes=15),
        suggestions=(),
        chosen_arc_ids=(),
        chapters=chapter_rows,
        script_lines=lines,
        scenes=(),
        unsourced_line_ids=(),
    )


def _prepared() -> PreparedChapterTTSRequest:
    return prepare_chapter_tts_request(
        _plan(),
        asset_id="asset-747",
        revision_id="revision-1",
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="alloy",
    )


def _authorization(digest: str) -> MultimediaExecutionAuthorizationV2:
    return issue_async_execution_authorization(
        signing_key=KEY,
        request_id="request-1",
        operator_id="operator-1",
        asset_id="asset-747",
        revision_id="revision-1",
        provider="openai",
        route_policy="balanced",
        model="gpt-4o-mini-tts",
        endpoint_capability="text-to-speech",
        catalog_version="catalog-1",
        catalog_digest=CATALOG_DIGEST,
        quote_id="quote-1",
        quote_expires_at=NOW + timedelta(hours=1),
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest=RECOVERY_DIGEST,
        approved_ceiling_microdollars=50_000,
        request_body_digest=digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def test_request_is_canonical_grounded_and_deterministic() -> None:
    first = _prepared()
    second = _prepared()
    assert first.body_json == second.body_json
    assert first.body_digest == second.body_digest
    assert first.text == "Grounded chapter 0 explains the evidence."
    assert first.script_line_ids == ("chapter-0-line-0",)
    assert first.paragraph_ids == ("para-chapter-0-line-0",)
    assert first.source_chunk_ids == ("chunk-0",)
    assert "\\n" not in first.body_json


def test_authorization_is_bound_to_exact_prepared_body() -> None:
    prepared = _prepared()
    verify_chapter_tts_authorization(
        _authorization(prepared.body_digest),
        prepared,
        signing_key=KEY,
        operator_id="operator-1",
        catalog_version="catalog-1",
        catalog_digest=CATALOG_DIGEST,
        quote_id="quote-1",
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest=RECOVERY_DIGEST,
        approved_ceiling_microdollars=50_000,
        now=NOW,
    )


def test_body_or_execution_binding_mismatch_fails_closed() -> None:
    prepared = _prepared()
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="request_body_digest"):
        verify_chapter_tts_authorization(
            _authorization("0" * 64),
            prepared,
            signing_key=KEY,
            operator_id="operator-1",
            catalog_version="catalog-1",
            catalog_digest=CATALOG_DIGEST,
            quote_id="quote-1",
            recovery_authority_id="recovery-1",
            recovery_verification_key_digest=RECOVERY_DIGEST,
            approved_ceiling_microdollars=50_000,
            now=NOW,
        )


def test_multi_chapter_and_invalid_media_shape_rejected_before_execution() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        prepare_chapter_tts_request(
            _plan(chapters=2),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
        )
    with pytest.raises(ValueError, match="audio shape"):
        prepare_chapter_tts_request(
            _plan(),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
            sample_rate_hz=1,
        )


def test_identifiers_and_speed_cannot_escape_canonical_request() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        prepare_chapter_tts_request(
            _plan(),
            asset_id="../escape",
            revision_id="revision",
            provider="openai",
            model="tts",
        )
    with pytest.raises(ValueError, match="speed"):
        prepare_chapter_tts_request(
            _plan(),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
            speed=float("nan"),
        )
