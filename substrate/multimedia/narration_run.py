"""Crash-safe multi-chapter narration runs over authorized chapter TTS receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from runtime.db_lock import FlockWriteCoordinator, WriteContext, connect_read
from substrate.contracts.multimedia import GeneratedFile

from .audio_assembly import ChapterAudio
from .chapter_tts_production import (
    ChapterTTSSynthesisResult,
    PreparedChapterTTSRequest,
    prepare_chapter_tts_request,
    produce_chapter_narration,
    verify_chapter_tts_authorization,
)
from .execution_authorization import MultimediaExecutionAuthorizationV2
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .narration_production import NarrationProductionArtifact, produce_narration_track
from .planner import MultimediaPlan
from .provider_execution import (
    ProviderExecutionRecord,
    begin_reserved_provider_submission_set,
)

_MAX_CHAPTERS = 64
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

_RUN_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_narration_runs (
    run_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    authorization_set_digest TEXT NOT NULL,
    chapter_bindings_json TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_json TEXT,
    run_mac TEXT NOT NULL
)
"""


class NarrationRunError(RuntimeError):
    """A narration run receipt or aggregate publication is invalid."""


@dataclass(frozen=True)
class PreparedNarrationRun:
    asset_id: str
    revision_id: str
    chapters: tuple[PreparedChapterTTSRequest, ...]


@dataclass(frozen=True)
class AuthorizedNarrationRun:
    run_id: str
    asset_id: str
    revision_id: str
    authorization_set_digest: str
    chapters: tuple[PreparedChapterTTSRequest, ...]


@dataclass(frozen=True)
class NarrationRunReceipt:
    run_id: str
    asset_id: str
    revision_id: str
    authorization_set_digest: str
    chapter_bindings_json: str
    status: str
    artifact_json: str | None
    run_mac: str


def prepare_narration_run(
    plan: MultimediaPlan,
    *,
    asset_id: str,
    revision_id: str,
    routes: Mapping[str, tuple[str, str]],
    voice: str = "narrator",
    speed: float = 1.0,
    sample_rate_hz: int = 24_000,
    channels: Literal[1, 2] = 1,
) -> PreparedNarrationRun:
    """Bind every spoken chapter to one deterministic child authorization."""
    asset_id = _identifier("asset_id", asset_id)
    revision_id = _identifier("revision_id", revision_id)
    chapter_ids = tuple(
        chapter.chapter_id
        for chapter in plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in plan.script_lines
        )
    )
    if not chapter_ids or len(chapter_ids) > _MAX_CHAPTERS:
        raise ValueError("narration run requires one through 64 spoken chapters")
    if set(routes) != set(chapter_ids):
        raise ValueError("routes must exactly cover spoken chapters")
    prepared: list[PreparedChapterTTSRequest] = []
    for sequence, chapter_id in enumerate(chapter_ids):
        provider, model = routes[chapter_id]
        child_revision = _child_revision(revision_id, chapter_id, sequence)
        request = prepare_chapter_tts_request(
            plan,
            asset_id=asset_id,
            revision_id=child_revision,
            provider=provider,
            model=model,
            chapter_id=chapter_id,
            voice=voice,
            speed=speed,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
        )
        prepared.append(request)
    return PreparedNarrationRun(
        asset_id=asset_id,
        revision_id=revision_id,
        chapters=tuple(prepared),
    )


def authorize_narration_run(
    prepared: PreparedNarrationRun,
    authorizations: Mapping[str, MultimediaExecutionAuthorizationV2],
) -> AuthorizedNarrationRun:
    if set(authorizations) != {row.chapter_id for row in prepared.chapters}:
        raise ValueError("authorizations must exactly cover prepared chapters")
    set_rows: list[list[object]] = []
    for sequence, request in enumerate(prepared.chapters):
        authorization = authorizations[request.chapter_id]
        if (
            authorization.asset_id != request.asset_id
            or authorization.revision_id != request.revision_id
            or authorization.provider != request.provider
            or authorization.model != request.model
            or authorization.request_body_digest != request.body_digest
        ):
            raise ValueError("authorization conflicts with prepared chapter request")
        set_rows.append(
            [sequence, request.chapter_id, request.revision_id, request.body_digest,
             authorization.authorization_id, authorization.approved_ceiling_microdollars]
        )
    set_digest = hashlib.sha256(
        json.dumps(set_rows, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    run_id = "mmnrun_" + hashlib.sha256(
        json.dumps(
            [prepared.asset_id, prepared.revision_id, set_digest], separators=(",", ":")
        ).encode()
    ).hexdigest()
    return AuthorizedNarrationRun(
        run_id=run_id,
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        authorization_set_digest=set_digest,
        chapters=prepared.chapters,
    )


def produce_narration_run(
    *,
    plan: MultimediaPlan,
    prepared: AuthorizedNarrationRun,
    authorizations: Mapping[str, MultimediaExecutionAuthorizationV2],
    operator_id: str,
    signing_key: bytes,
    integrity_key: bytes,
    db_path: str,
    output_dir: str,
    now: datetime,
    synthesize: Callable[
        [PreparedChapterTTSRequest], ChapterTTSSynthesisResult
    ],
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    timeout_seconds: int = 300,
) -> NarrationProductionArtifact:
    """Admit all chapter ceilings, resume each child, then seal one aggregate."""
    expected_requests = prepare_narration_run(
        plan,
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        routes={
            chapter_id: (authorization.provider, authorization.model)
            for chapter_id, authorization in authorizations.items()
        },
        voice=prepared.chapters[0].voice,
        speed=prepared.chapters[0].speed,
        sample_rate_hz=prepared.chapters[0].sample_rate_hz,
        channels=prepared.chapters[0].channels,
    )
    expected = authorize_narration_run(expected_requests, authorizations)
    if expected != prepared:
        raise ValueError("prepared narration run conflicts with plan or authorizations")
    receipt = _get_run(db_path, prepared.run_id, signing_key)
    if receipt is None:
        for request in prepared.chapters:
            authorization = authorizations[request.chapter_id]
            verify_chapter_tts_authorization(
                authorization,
                request,
                signing_key=signing_key,
                operator_id=operator_id,
                catalog_version=authorization.catalog_version,
                catalog_digest=authorization.catalog_digest,
                quote_id=authorization.quote_id,
                recovery_authority_id=authorization.recovery_authority_id,
                recovery_verification_key_digest=(
                    authorization.recovery_verification_key_digest
                ),
                approved_ceiling_microdollars=(
                    authorization.approved_ceiling_microdollars
                ),
                now=now,
            )
        ordered_authorizations = tuple(
            authorizations[row.chapter_id] for row in prepared.chapters
        )
        try:
            begin_reserved_provider_submission_set(
                db_path=db_path,
                authorizations=ordered_authorizations,
                signing_key=signing_key,
                now=now,
                mutation=lambda ctx, rows: _admit_run(
                    ctx, rows, prepared=prepared, signing_key=signing_key
                ),
            )
        except RuntimeError:
            raced = _get_run(db_path, prepared.run_id, signing_key)
            if raced is None:
                raise
            receipt = raced
        else:
            receipt = _require_run(db_path, prepared.run_id, signing_key)
    _verify_run(receipt, prepared)
    if receipt.status == "sealed":
        return _reopen_run(receipt, prepared, integrity_key)

    children: list[NarrationProductionArtifact] = []
    for request in prepared.chapters:
        authorization = authorizations[request.chapter_id]
        children.append(
            produce_chapter_narration(
                plan=plan,
                prepared=request,
                authorization=authorization,
                signing_key=signing_key,
                integrity_key=integrity_key,
                operator_id=operator_id,
                catalog_version=authorization.catalog_version,
                catalog_digest=authorization.catalog_digest,
                quote_id=authorization.quote_id,
                recovery_authority_id=authorization.recovery_authority_id,
                recovery_verification_key_digest=(
                    authorization.recovery_verification_key_digest
                ),
                approved_ceiling_microdollars=(
                    authorization.approved_ceiling_microdollars
                ),
                db_path=db_path,
                output_dir=output_dir,
                now=now,
                synthesize=synthesize,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                timeout_seconds=timeout_seconds,
            )
        )

    destination = Path(output_dir) / (
        f"{prepared.asset_id}-{prepared.revision_id}-narration"
    )
    if destination.is_symlink():
        raise NarrationRunError("aggregate narration destination cannot be a symlink")
    if destination.exists() and not destination.is_dir():
        raise NarrationRunError("aggregate narration destination is not a directory")
    if destination.is_dir():
        artifact = NarrationProductionArtifact.reopen(
            (destination / "narration.json").read_bytes(), integrity_key
        )
    else:
        try:
            artifact = _produce_aggregate(
                prepared=prepared,
                children=tuple(children),
                integrity_key=integrity_key,
                output_dir=output_dir,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                timeout_seconds=timeout_seconds,
            )
        except FileExistsError:
            raise NarrationRunError("aggregate narration publication is in flight") from None
    _verify_aggregate_children(artifact, prepared, tuple(children))
    _seal_run(db_path, prepared.run_id, artifact, signing_key)
    return _reopen_run(
        _require_run(db_path, prepared.run_id, signing_key),
        prepared,
        integrity_key,
    )


def get_narration_run(
    *, db_path: str, run_id: str, signing_key: bytes
) -> NarrationRunReceipt:
    return _require_run(db_path, run_id, signing_key)


def list_narration_runs(
    *, db_path: str, asset_id: str, revision_id: str, signing_key: bytes
) -> tuple[NarrationRunReceipt, ...]:
    """Read and MAC-verify every persisted run for one exact parent revision."""
    _identifier("asset_id", asset_id)
    _identifier("revision_id", revision_id)
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    if not Path(db_path).is_file():
        return ()
    try:
        with connect_read(db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM multimedia_narration_runs "
                "WHERE asset_id=? AND revision_id=? ORDER BY run_id",
                [asset_id, revision_id],
            ).fetchall()
    except Exception as exc:
        raise NarrationRunError("narration run set is unavailable") from exc
    return tuple(_receipt(tuple(row), signing_key) for row in rows)


def _produce_aggregate(
    *,
    prepared: AuthorizedNarrationRun,
    children: tuple[NarrationProductionArtifact, ...],
    integrity_key: bytes,
    output_dir: str,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout_seconds: int,
) -> NarrationProductionArtifact:
    if len(children) != len(prepared.chapters):
        raise NarrationRunError("child narration set is incomplete")
    chapters: list[ChapterAudio] = []
    files: list[GeneratedFile] = []
    paths: dict[str, str] = {}
    offset = 0.0
    for sequence, (request, child) in enumerate(zip(prepared.chapters, children, strict=True)):
        manifest = child.manifest
        if (
            manifest.asset_id != prepared.asset_id
            or manifest.revision_id != request.revision_id
            or tuple(row.chapter_id for row in manifest.sources) != (request.chapter_id,)
        ):
            raise NarrationRunError("child narration identity conflicts")
        audio_id = f"run-audio-{sequence}"
        duration = manifest.duration_seconds
        chapters.append(
            ChapterAudio(
                chapter_id=request.chapter_id,
                title=request.title,
                sequence=sequence,
                audio_file_id=audio_id,
                duration_seconds=duration,
                start_offset_seconds=offset,
                script_line_ids=request.script_line_ids,
                source_chunk_ids=request.source_chunk_ids,
                paragraph_ids=request.paragraph_ids,
                recap_prompt="Recall the evidence.",
            )
        )
        files.append(
            GeneratedFile(
                file_id=audio_id,
                kind="audio",
                storage_uri=(
                    f"antiek-mm://{prepared.asset_id}/{prepared.revision_id}/{audio_id}.wav"
                ),
                sha256=manifest.output_sha256,
                mime="audio/wav",
                provider=request.provider,
                duration_seconds=duration,
            )
        )
        paths[audio_id] = manifest.output_path
        offset = round(offset + duration, 3)
    return produce_narration_track(
        asset_id=prepared.asset_id,
        revision_id=prepared.revision_id,
        chapters=tuple(chapters),
        generated_files=tuple(files),
        chapter_paths=paths,
        output_dir=output_dir,
        integrity_key=integrity_key,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        sample_rate_hz=prepared.chapters[0].sample_rate_hz,
        channels=prepared.chapters[0].channels,
        timeout_seconds=timeout_seconds,
    )


def _verify_aggregate_children(
    artifact: NarrationProductionArtifact,
    prepared: AuthorizedNarrationRun,
    children: tuple[NarrationProductionArtifact, ...],
) -> None:
    manifest = artifact.manifest
    if (
        manifest.asset_id != prepared.asset_id
        or manifest.revision_id != prepared.revision_id
        or len(manifest.sources) != len(children)
        or tuple(row.chapter_id for row in manifest.sources)
        != tuple(row.chapter_id for row in prepared.chapters)
        or tuple(row.sha256 for row in manifest.sources)
        != tuple(row.manifest.output_sha256 for row in children)
        or tuple(row.duration_seconds for row in manifest.sources)
        != tuple(row.manifest.duration_seconds for row in children)
        or tuple(
            (
                row.chapter_id,
                row.script_line_ids,
                row.source_chunk_ids,
                row.paragraph_ids,
            )
            for row in manifest.chapter_bindings
        )
        != tuple(
            (
                row.chapter_id,
                row.script_line_ids,
                row.source_chunk_ids,
                row.paragraph_ids,
            )
            for row in prepared.chapters
        )
        or manifest.duration_seconds
        != round(sum(row.manifest.duration_seconds for row in children), 3)
    ):
        raise NarrationRunError("aggregate narration conflicts with sealed child set")


def _admit_run(
    ctx: WriteContext,
    rows: tuple[tuple[ProviderExecutionRecord, object], ...],
    *,
    prepared: AuthorizedNarrationRun,
    signing_key: bytes,
) -> None:
    if len(rows) != len(prepared.chapters):
        raise NarrationRunError("reserved provider set is incomplete")
    ctx.execute(_RUN_DDL)
    existing = ctx.execute(
        "SELECT * FROM multimedia_narration_runs WHERE run_id = ?", [prepared.run_id]
    ).fetchone()
    if existing is not None:
        _verify_run(_receipt(existing, signing_key), prepared)
        return
    values: list[object] = [
        prepared.run_id,
        prepared.asset_id,
        prepared.revision_id,
        prepared.authorization_set_digest,
        _chapter_bindings(prepared),
        "admitted",
        None,
    ]
    ctx.execute(
        "INSERT INTO multimedia_narration_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [*values, _run_mac(values, signing_key)],
    )


def _seal_run(
    db_path: str,
    run_id: str,
    artifact: NarrationProductionArtifact,
    signing_key: bytes,
) -> None:
    payload = artifact.to_json()
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.narration_run.seal") as ctx:
        row = ctx.execute(
            "SELECT * FROM multimedia_narration_runs WHERE run_id = ?", [run_id]
        ).fetchone()
        if row is None:
            raise NarrationRunError("narration run disappeared")
        current = _receipt(row, signing_key)
        if current.status == "sealed":
            if current.artifact_json != payload:
                raise NarrationRunError("sealed narration run conflicts")
            return
        values: list[object] = [*row[:5], "sealed", payload]
        ctx.execute(
            "UPDATE multimedia_narration_runs SET status='sealed', artifact_json=?, run_mac=? "
            "WHERE run_id=? AND status='admitted'",
            [payload, _run_mac(values, signing_key), run_id],
        )


def _get_run(
    db_path: str, run_id: str, signing_key: bytes
) -> NarrationRunReceipt | None:
    if not Path(db_path).exists():
        return None
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.narration_run.read") as ctx:
        ctx.execute(_RUN_DDL)
        row = ctx.execute(
            "SELECT * FROM multimedia_narration_runs WHERE run_id = ?", [run_id]
        ).fetchone()
    return None if row is None else _receipt(row, signing_key)


def _require_run(
    db_path: str, run_id: str, signing_key: bytes
) -> NarrationRunReceipt:
    result = _get_run(db_path, run_id, signing_key)
    if result is None:
        raise NarrationRunError("narration run does not exist")
    return result


def _receipt(row: tuple[object, ...], signing_key: bytes) -> NarrationRunReceipt:
    if len(row) != 8 or not isinstance(row[7], str):
        raise NarrationRunError("narration run shape is invalid")
    if not hmac.compare_digest(row[7], _run_mac(list(row[:7]), signing_key)):
        raise NarrationRunError("narration run MAC is invalid")
    if row[5] not in {"admitted", "sealed"}:
        raise NarrationRunError("narration run status is invalid")
    return NarrationRunReceipt(
        run_id=str(row[0]),
        asset_id=str(row[1]),
        revision_id=str(row[2]),
        authorization_set_digest=str(row[3]),
        chapter_bindings_json=str(row[4]),
        status=str(row[5]),
        artifact_json=str(row[6]) if row[6] is not None else None,
        run_mac=row[7],
    )


def _verify_run(receipt: NarrationRunReceipt, prepared: AuthorizedNarrationRun) -> None:
    if (
        receipt.run_id != prepared.run_id
        or receipt.asset_id != prepared.asset_id
        or receipt.revision_id != prepared.revision_id
        or receipt.authorization_set_digest != prepared.authorization_set_digest
        or receipt.chapter_bindings_json != _chapter_bindings(prepared)
    ):
        raise NarrationRunError("narration run receipt conflicts")


def _reopen_run(
    receipt: NarrationRunReceipt,
    prepared: AuthorizedNarrationRun,
    integrity_key: bytes,
) -> NarrationProductionArtifact:
    _verify_run(receipt, prepared)
    if receipt.status != "sealed" or receipt.artifact_json is None:
        raise NarrationRunError("narration run is not sealed")
    artifact = NarrationProductionArtifact.reopen(receipt.artifact_json, integrity_key)
    if (
        artifact.manifest.asset_id != prepared.asset_id
        or artifact.manifest.revision_id != prepared.revision_id
        or tuple(row.chapter_id for row in artifact.manifest.sources)
        != tuple(row.chapter_id for row in prepared.chapters)
        or tuple(
            (
                row.chapter_id,
                row.script_line_ids,
                row.source_chunk_ids,
                row.paragraph_ids,
            )
            for row in artifact.manifest.chapter_bindings
        )
        != tuple(
            (
                row.chapter_id,
                row.script_line_ids,
                row.source_chunk_ids,
                row.paragraph_ids,
            )
            for row in prepared.chapters
        )
    ):
        raise NarrationRunError("aggregate narration identity conflicts")
    return artifact


def _child_revision(parent_revision: str, chapter_id: str, sequence: int) -> str:
    digest = hashlib.sha256(
        json.dumps([parent_revision, chapter_id, sequence], separators=(",", ":")).encode()
    ).hexdigest()[:32]
    return f"tts-{digest}"


def narration_child_revision(parent_revision: str, chapter_id: str, sequence: int) -> str:
    """Return the child revision shared by narration authorization and execution."""
    return _child_revision(parent_revision, chapter_id, sequence)


def _chapter_bindings(prepared: AuthorizedNarrationRun) -> str:
    return json.dumps(
        [
            [
                row.chapter_id,
                list(row.script_line_ids),
                list(row.source_chunk_ids),
                list(row.paragraph_ids),
            ]
            for row in prepared.chapters
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _identifier(field: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _run_mac(values: list[object], signing_key: bytes) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hmac.new(signing_key, payload, hashlib.sha256).hexdigest()


__all__ = [
    "NarrationRunError",
    "NarrationRunReceipt",
    "AuthorizedNarrationRun",
    "PreparedNarrationRun",
    "authorize_narration_run",
    "get_narration_run",
    "list_narration_runs",
    "narration_child_revision",
    "prepare_narration_run",
    "produce_narration_run",
]
