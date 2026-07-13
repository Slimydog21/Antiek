"""All-or-nothing server composition for authorized multimedia production."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from substrate.multimedia.authorized_production_worker import AuthorizedProductionRuntime
from substrate.multimedia.diagram_evidence_authority import DiagramEvidenceAuthority
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.reviewed_visual_registry import ReviewedVisualRegistry
from substrate.multimedia.tts_gateway import GatewayPoster, TTSSynthesisGateway
from substrate.multimedia.verified_playback import VerifiedPlaybackRuntime
from substrate.multimedia.visual_evidence_authority import VisualEvidenceAuthority

_PREFIX = "ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_"


def multimedia_production_worker_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
    gateway_poster: GatewayPoster | None = None,
) -> AuthorizedProductionRuntime | None:
    values = os.environ if environ is None else environ
    enabled = values.get(f"{_PREFIX}ENABLED", "").strip().lower()
    names = (
        "DB_PATH",
        "SIGNING_KEY_HEX",
        "NARRATION_KEY_HEX",
        "VISUAL_KEY_HEX",
        "EVIDENCE_KEY_HEX",
        "RENDER_KEY_HEX",
        "RECEIPT_KEY_HEX",
        "NARRATION_OUTPUT_DIR",
        "VISUAL_OUTPUT_DIR",
        "RENDER_OUTPUT_DIR",
        "RECEIPT_OUTPUT_DIR",
        "REVIEWED_VISUAL_DB_PATH",
        "REVIEWED_VISUAL_KEY_HEX",
        "VISUAL_EVIDENCE_DB_PATH",
        "VISUAL_OPERATOR_VERIFY_KEY_HEX",
        "VISUAL_REVIEWER_IDS",
        "TTS_GATEWAY_URL",
        "TTS_GATEWAY_TOKEN",
        "TTS_ACCOUNT_IDENTITY_DIGEST",
        "TTS_GATEWAY_TIMEOUT_SECONDS",
        "FFMPEG_PATH",
        "FFPROBE_PATH",
        "WIDTH_PX",
        "HEIGHT_PX",
        "FPS",
        "TIMEOUT_SECONDS",
    )
    fields = {name: values.get(f"{_PREFIX}{name}", "").strip() for name in names}
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not value for value in fields.values()):
        raise RuntimeError("multimedia production worker configuration is incomplete")
    try:
        signing_key = _key(fields["SIGNING_KEY_HEX"], "signing")
        narration_key = _key(fields["NARRATION_KEY_HEX"], "narration")
        visual_key = _key(fields["VISUAL_KEY_HEX"], "visual")
        evidence_key = _key(fields["EVIDENCE_KEY_HEX"], "evidence")
        render_key = _key(fields["RENDER_KEY_HEX"], "render")
        receipt_key = _key(fields["RECEIPT_KEY_HEX"], "receipt")
        reviewed_key = _key(fields["REVIEWED_VISUAL_KEY_HEX"], "reviewed visual")
        verify_key = bytes.fromhex(fields["VISUAL_OPERATOR_VERIFY_KEY_HEX"])
        gateway_timeout = float(fields["TTS_GATEWAY_TIMEOUT_SECONDS"])
        width = int(fields["WIDTH_PX"])
        height = int(fields["HEIGHT_PX"])
        fps = int(fields["FPS"])
        timeout = int(fields["TIMEOUT_SECONDS"])
    except ValueError:
        raise RuntimeError("multimedia production worker configuration is invalid") from None
    if len(verify_key) != 32:
        raise RuntimeError("multimedia production worker configuration is invalid")
    if len(
        {
            signing_key,
            narration_key,
            visual_key,
            evidence_key,
            render_key,
            receipt_key,
            reviewed_key,
        }
    ) != 7:
        raise RuntimeError("multimedia production worker keys must be independent")
    reviewers = frozenset(
        value.strip()
        for value in fields["VISUAL_REVIEWER_IDS"].split(",")
        if value.strip()
    )
    if not reviewers or len(reviewers) > 32:
        raise RuntimeError("multimedia production worker configuration is invalid")
    if not (16 <= width <= 3840 and 16 <= height <= 2160 and 1 <= fps <= 60):
        raise RuntimeError("multimedia production worker configuration is invalid")
    if timeout < 1 or timeout > 3600:
        raise RuntimeError("multimedia production worker configuration is invalid")
    for name in (
        "NARRATION_OUTPUT_DIR",
        "VISUAL_OUTPUT_DIR",
        "RENDER_OUTPUT_DIR",
        "RECEIPT_OUTPUT_DIR",
    ):
        _private_directory(fields[name])
    for name in ("DB_PATH", "REVIEWED_VISUAL_DB_PATH", "VISUAL_EVIDENCE_DB_PATH"):
        _private_parent(fields[name])
    _executable(fields["FFMPEG_PATH"])
    _executable(fields["FFPROBE_PATH"])

    gateway = TTSSynthesisGateway(
        endpoint_url=fields["TTS_GATEWAY_URL"],
        bearer_token=fields["TTS_GATEWAY_TOKEN"],
        account_identity_digest=fields["TTS_ACCOUNT_IDENTITY_DIGEST"],
        timeout_seconds=gateway_timeout,
        poster=gateway_poster,
    )
    reviewed_registry = ReviewedVisualRegistry(
        db_path=fields["REVIEWED_VISUAL_DB_PATH"], integrity_key=reviewed_key
    )
    playback = VerifiedPlaybackRuntime(
        receipt_root=fields["RECEIPT_OUTPUT_DIR"],
        receipt_key=receipt_key,
        narration_key=narration_key,
        visual_key=visual_key,
        render_key=render_key,
    )
    evidence = VisualEvidenceAuthority(
        db_path=fields["VISUAL_EVIDENCE_DB_PATH"],
        operator_verify_key=verify_key,
        evidence_authority_key=evidence_key,
        authorized_reviewer_ids=reviewers,
    )
    composite_evidence = DiagramEvidenceAuthority(
        db_path=fields["VISUAL_EVIDENCE_DB_PATH"],
        operator_verify_key=verify_key,
        evidence_authority_key=evidence_key,
        authorized_reviewer_ids=reviewers,
        fallback=evidence,
    )
    return AuthorizedProductionRuntime(
        store=store,
        reviewed_visual_registry=reviewed_registry,
        playback=playback,
        signing_key=signing_key,
        narration_integrity_key=narration_key,
        visual_integrity_key=visual_key,
        evidence_authority_key=evidence_key,
        render_integrity_key=render_key,
        receipt_key=receipt_key,
        db_path=fields["DB_PATH"],
        narration_output_dir=fields["NARRATION_OUTPUT_DIR"],
        visual_output_dir=fields["VISUAL_OUTPUT_DIR"],
        render_output_dir=fields["RENDER_OUTPUT_DIR"],
        receipt_output_dir=fields["RECEIPT_OUTPUT_DIR"],
        synthesize=gateway,
        verify_evidence=composite_evidence,
        clock=lambda: datetime.now(UTC),
        ffmpeg_path=fields["FFMPEG_PATH"],
        ffprobe_path=fields["FFPROBE_PATH"],
        width_px=width,
        height_px=height,
        fps=fps,
        timeout_seconds=timeout,
    )


def _key(value: str, name: str) -> bytes:
    try:
        decoded = bytes.fromhex(value)
    except ValueError:
        raise ValueError(f"{name} key is invalid") from None
    if len(decoded) < 32:
        raise ValueError(f"{name} key is invalid")
    return decoded


def _private_directory(value: str) -> None:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError("multimedia production private directory is unavailable") from exc
    if (
        not path.is_absolute()
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise RuntimeError("multimedia production private directory is invalid")


def _private_parent(value: str) -> None:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("multimedia production database path is invalid")
    _private_directory(str(path.parent))


def _executable(value: str) -> None:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError("multimedia production executable is unavailable") from exc
    if (
        not path.is_absolute()
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or not os.access(path, os.X_OK)
    ):
        raise RuntimeError("multimedia production executable is invalid")


__all__ = ["multimedia_production_worker_runtime_from_environment"]
