"""All-or-nothing composition for the cheapest local audible workstation."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from substrate.multimedia.local_audible_coordinator import LocalAudibleCoordinator
from substrate.multimedia.local_audible_workstation import LocalAudibleWorkstationRuntime
from substrate.multimedia.local_tts import LocalTTSAdapter, LocalTTSConfig
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.verified_audio_playback import VerifiedAudioPlaybackRuntime

from .multimedia_local_runtime import _key, _private_directory, _private_parent, _private_regular

_PREFIX = "ANTIEK_MULTIMEDIA_LOCAL_"


@dataclass(frozen=True)
class MultimediaLocalAudibleRuntime:
    workstation: LocalAudibleWorkstationRuntime
    playback: VerifiedAudioPlaybackRuntime
    store: MultimediaAssetStore


def multimedia_local_audible_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
) -> MultimediaLocalAudibleRuntime | None:
    values = os.environ if environ is None else environ
    names = (
        "DB_PATH",
        "WORKSTATION_KEY_HEX",
        "TTS_KEY_HEX",
        "COORDINATOR_KEY_HEX",
        "NARRATION_KEY_HEX",
        "RECEIPT_KEY_HEX",
        "TTS_OUTPUT_DIR",
        "NARRATION_OUTPUT_DIR",
        "SAY_PATH",
        "FFMPEG_PATH",
        "FFPROBE_PATH",
        "VOICE",
        "WORDS_PER_MINUTE",
        "TIMEOUT_SECONDS",
    )
    enabled = values.get(f"{_PREFIX}ENABLED", "").strip().lower()
    fields = {name: values.get(f"{_PREFIX}{name}", "").strip() for name in names}
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not value for value in fields.values()):
        raise RuntimeError("local audible runtime configuration is incomplete")
    try:
        workstation_key = _derive(_key(fields["WORKSTATION_KEY_HEX"]), b"audible-workstation")
        coordinator_key = _derive(_key(fields["COORDINATOR_KEY_HEX"]), b"audible-coordinator")
        production_key = _derive(_key(fields["NARRATION_KEY_HEX"]), b"audible-production")
        receipt_key = _derive(_key(fields["RECEIPT_KEY_HEX"]), b"audible-receipt")
        tts_key = _key(fields["TTS_KEY_HEX"])
        words_per_minute = int(fields["WORDS_PER_MINUTE"])
        timeout = int(fields["TIMEOUT_SECONDS"])
    except ValueError:
        raise RuntimeError("local audible runtime configuration is invalid") from None
    if (
        len({workstation_key, coordinator_key, production_key, receipt_key, tts_key}) != 5
        or not 80 <= words_per_minute <= 450
        or not 1 <= timeout <= 900
    ):
        raise RuntimeError("local audible runtime configuration is invalid")
    _private_parent(fields["DB_PATH"])
    for name in ("TTS_OUTPUT_DIR", "NARRATION_OUTPUT_DIR"):
        _private_directory(fields[name])
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
        signing_key=tts_key,
    )
    coordinator = LocalAudibleCoordinator(
        db_path=fields["DB_PATH"],
        signing_key=coordinator_key,
        production_integrity_key=production_key,
        receipt_key=receipt_key,
        output_dir=fields["NARRATION_OUTPUT_DIR"],
        store=store,
        tts_resolver=tts,
        ffmpeg_path=fields["FFMPEG_PATH"],
        ffprobe_path=fields["FFPROBE_PATH"],
        timeout_seconds=timeout,
    )
    workstation = LocalAudibleWorkstationRuntime(
        db_path=fields["DB_PATH"],
        signing_key=workstation_key,
        store=store,
        tts=tts,
        production=coordinator,
        clock=lambda: datetime.now(UTC),
    )
    playback = VerifiedAudioPlaybackRuntime(
        receipt_path_resolver=coordinator.receipt_path,
        receipt_key=receipt_key,
        production_integrity_key=production_key,
    )
    return MultimediaLocalAudibleRuntime(workstation, playback, store)


def _derive(key: bytes, label: bytes) -> bytes:
    return hmac.new(key, b"antiek.local." + label, hashlib.sha256).digest()


__all__ = [
    "MultimediaLocalAudibleRuntime",
    "multimedia_local_audible_runtime_from_environment",
]
