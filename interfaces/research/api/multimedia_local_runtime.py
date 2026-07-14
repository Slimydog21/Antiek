"""All-or-nothing zero-provider runtime composition for local multimedia."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from nacl.signing import SigningKey

from substrate.multimedia.diagram_evidence_authority import (
    DiagramEvidenceAuthority,
    DiagramEvidenceAuthorityError,
)
from substrate.multimedia.local_production_coordinator import (
    LocalProductionCoordinator,
    LocalVideoProductionCoordinator,
)
from substrate.multimedia.local_source_card import LocalSourceCardRegistry
from substrate.multimedia.local_tts import LocalTTSAdapter, LocalTTSConfig
from substrate.multimedia.local_workstation import LocalWorkstationRuntime
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.visual_selection import ReviewedVisualSelection, VerifiedVisualEvidence

_PREFIX = "ANTIEK_MULTIMEDIA_LOCAL_"


def multimedia_local_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
) -> LocalWorkstationRuntime | None:
    values = os.environ if environ is None else environ
    names = (
        "DB_PATH", "WORKSTATION_KEY_HEX", "TTS_KEY_HEX", "CARD_KEY_HEX",
        "COORDINATOR_KEY_HEX", "NARRATION_KEY_HEX", "VISUAL_KEY_HEX",
        "EVIDENCE_KEY_HEX", "RENDER_KEY_HEX", "RECEIPT_KEY_HEX",
        "OPERATOR_SIGNING_KEY_HEX", "REVIEWER_IDS", "TTS_OUTPUT_DIR",
        "CARD_OUTPUT_DIR", "NARRATION_OUTPUT_DIR", "VISUAL_OUTPUT_DIR",
        "RENDER_OUTPUT_DIR", "RECEIPT_OUTPUT_DIR", "FONT_PATH", "SAY_PATH",
        "FFMPEG_PATH", "FFPROBE_PATH", "VOICE", "WORDS_PER_MINUTE",
        "TIMEOUT_SECONDS",
    )
    enabled = values.get(f"{_PREFIX}ENABLED", "").strip().lower()
    fields = {name: values.get(f"{_PREFIX}{name}", "").strip() for name in names}
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not value for value in fields.values()):
        raise RuntimeError("local multimedia runtime configuration is incomplete")
    try:
        keys = {
            name: _key(fields[name])
            for name in (
                "WORKSTATION_KEY_HEX", "TTS_KEY_HEX", "CARD_KEY_HEX",
                "COORDINATOR_KEY_HEX", "NARRATION_KEY_HEX", "VISUAL_KEY_HEX",
                "EVIDENCE_KEY_HEX", "RENDER_KEY_HEX", "RECEIPT_KEY_HEX",
            )
        }
        operator_key = bytes.fromhex(fields["OPERATOR_SIGNING_KEY_HEX"])
        words_per_minute = int(fields["WORDS_PER_MINUTE"])
        timeout = int(fields["TIMEOUT_SECONDS"])
    except ValueError:
        raise RuntimeError("local multimedia runtime configuration is invalid") from None
    if (
        len(operator_key) != 32
        or len(set(keys.values()) | {operator_key}) != len(keys) + 1
        or not 80 <= words_per_minute <= 450
        or not 1 <= timeout <= 900
    ):
        raise RuntimeError("local multimedia runtime configuration is invalid")
    reviewers = frozenset(
        value.strip() for value in fields["REVIEWER_IDS"].split(",") if value.strip()
    )
    if not reviewers or len(reviewers) > 32:
        raise RuntimeError("local multimedia runtime configuration is invalid")
    _private_parent(fields["DB_PATH"])
    for name in (
        "TTS_OUTPUT_DIR", "CARD_OUTPUT_DIR", "NARRATION_OUTPUT_DIR",
        "VISUAL_OUTPUT_DIR", "RENDER_OUTPUT_DIR", "RECEIPT_OUTPUT_DIR",
    ):
        _private_directory(fields[name])
    _private_regular(fields["FONT_PATH"], executable=False)
    for name in ("SAY_PATH", "FFMPEG_PATH", "FFPROBE_PATH"):
        _private_regular(fields[name], executable=True)

    tts = LocalTTSAdapter(
        config=LocalTTSConfig(
            synthesizer_path=fields["SAY_PATH"],
            ffprobe_path=fields["FFPROBE_PATH"],
            output_dir=fields["TTS_OUTPUT_DIR"],
            voice=fields["VOICE"],
            words_per_minute=words_per_minute,
            timeout_seconds=timeout,
        ),
        db_path=fields["DB_PATH"],
        signing_key=keys["TTS_KEY_HEX"],
    )
    cards = LocalSourceCardRegistry(
        db_path=fields["DB_PATH"],
        output_dir=fields["CARD_OUTPUT_DIR"],
        font_path=fields["FONT_PATH"],
        integrity_key=keys["CARD_KEY_HEX"],
    )
    verify_key = bytes(SigningKey(operator_key).verify_key)

    def no_external_visual(
        _selection: ReviewedVisualSelection, _digest: str
    ) -> VerifiedVisualEvidence:
        raise DiagramEvidenceAuthorityError("external visual evidence is disabled")

    evidence = DiagramEvidenceAuthority(
        db_path=fields["DB_PATH"],
        operator_verify_key=verify_key,
        evidence_authority_key=keys["EVIDENCE_KEY_HEX"],
        authorized_reviewer_ids=reviewers,
        fallback=no_external_visual,
    )
    narration = LocalProductionCoordinator(
        db_path=fields["DB_PATH"],
        signing_key=keys["COORDINATOR_KEY_HEX"],
        narration_integrity_key=keys["NARRATION_KEY_HEX"],
        narration_output_dir=fields["NARRATION_OUTPUT_DIR"],
        store=store,
        tts_resolver=tts,
        ffmpeg_path=fields["FFMPEG_PATH"],
        ffprobe_path=fields["FFPROBE_PATH"],
        timeout_seconds=timeout,
    )
    video = LocalVideoProductionCoordinator(
        narration_coordinator=narration,
        source_card_resolver=cards,
        verify_evidence=evidence,
        visual_output_dir=fields["VISUAL_OUTPUT_DIR"],
        render_output_dir=fields["RENDER_OUTPUT_DIR"],
        receipt_output_dir=fields["RECEIPT_OUTPUT_DIR"],
        visual_integrity_key=keys["VISUAL_KEY_HEX"],
        evidence_authority_key=keys["EVIDENCE_KEY_HEX"],
        render_integrity_key=keys["RENDER_KEY_HEX"],
        receipt_integrity_key=keys["RECEIPT_KEY_HEX"],
    )
    return LocalWorkstationRuntime(
        db_path=fields["DB_PATH"],
        signing_key=keys["WORKSTATION_KEY_HEX"],
        operator_signing_key=operator_key,
        store=store,
        tts=tts,
        cards=cards,
        video=video,
        verify_evidence=evidence,
        clock=lambda: datetime.now(UTC),
    )


def _key(value: str) -> bytes:
    decoded = bytes.fromhex(value)
    if len(decoded) < 32:
        raise ValueError("key is invalid")
    return decoded


def _private_directory(value: str) -> None:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError("local multimedia private directory is unavailable") from exc
    if (
        not path.is_absolute() or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RuntimeError("local multimedia private directory is invalid")


def _private_parent(value: str) -> None:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("local multimedia database path is invalid")
    _private_directory(str(path.parent))


def _private_regular(value: str, *, executable: bool) -> None:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
        parent = resolved.parent.stat()
    except OSError as exc:
        raise RuntimeError("local multimedia local resource is unavailable") from exc
    if (
        not path.is_absolute() or not stat.S_ISREG(info.st_mode)
        or info.st_uid not in {0, os.getuid()} or parent.st_mode & 0o022
        or (executable and not info.st_mode & 0o111)
        or (not executable and not 0 < info.st_size <= 32 * 1024 * 1024)
    ):
        raise RuntimeError("local multimedia local resource is invalid")


__all__ = ["multimedia_local_runtime_from_environment"]
