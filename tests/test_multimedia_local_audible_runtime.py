from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

import interfaces.research.api.multimedia_local_audible_runtime as runtime_module
from interfaces.research.api.multimedia_local_audible_runtime import (
    MultimediaLocalAudibleRuntime,
    multimedia_local_audible_runtime_from_environment,
)

PREFIX = "ANTIEK_MULTIMEDIA_LOCAL_"


def _environment(tmp_path: Path) -> dict[str, str]:
    keys = {
        name: (bytes([index + 1]) * 32).hex()
        for index, name in enumerate(
            (
                "WORKSTATION_KEY_HEX",
                "TTS_KEY_HEX",
                "COORDINATOR_KEY_HEX",
                "NARRATION_KEY_HEX",
                "RECEIPT_KEY_HEX",
            )
        )
    }
    return {
        f"{PREFIX}ENABLED": "true",
        f"{PREFIX}DB_PATH": str(tmp_path / "local.duckdb"),
        f"{PREFIX}TTS_OUTPUT_DIR": str(tmp_path / "tts"),
        f"{PREFIX}NARRATION_OUTPUT_DIR": str(tmp_path / "audio"),
        f"{PREFIX}SAY_PATH": "/usr/bin/say",
        f"{PREFIX}FFMPEG_PATH": "/opt/homebrew/bin/ffmpeg",
        f"{PREFIX}FFPROBE_PATH": "/opt/homebrew/bin/ffprobe",
        f"{PREFIX}VOICE": "Samantha",
        f"{PREFIX}WORDS_PER_MINUTE": "180",
        f"{PREFIX}TIMEOUT_SECONDS": "300",
        **{f"{PREFIX}{name}": value for name, value in keys.items()},
    }


def test_absent_is_none_and_partial_fails(tmp_path: Path) -> None:
    assert (
        multimedia_local_audible_runtime_from_environment(
            store=object(), environ={}  # type: ignore[arg-type]
        )
        is None
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_local_audible_runtime_from_environment(
            store=object(),  # type: ignore[arg-type]
            environ={f"{PREFIX}ENABLED": "true"},
        )


def test_composes_domain_separated_local_authorities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = _environment(tmp_path)
    created = {}

    def capture(name):  # noqa: ANN001, ANN202
        def factory(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            result = (
                SimpleNamespace(receipt_path=lambda _asset, _revision: "/receipt")
                if name == "LocalAudibleCoordinator"
                else object()
            )
            created[name] = (args, kwargs, result)
            return result

        return factory

    for validator in ("_private_parent", "_private_directory", "_private_regular"):
        monkeypatch.setattr(runtime_module, validator, lambda *args, **kwargs: None)
    for name in (
        "LocalTTSAdapter",
        "LocalAudibleCoordinator",
        "LocalAudibleWorkstationRuntime",
        "VerifiedAudioPlaybackRuntime",
    ):
        monkeypatch.setattr(runtime_module, name, capture(name))
    result = multimedia_local_audible_runtime_from_environment(
        store=object(), environ=values  # type: ignore[arg-type]
    )
    assert isinstance(result, MultimediaLocalAudibleRuntime)
    assert set(created) == {
        "LocalTTSAdapter",
        "LocalAudibleCoordinator",
        "LocalAudibleWorkstationRuntime",
        "VerifiedAudioPlaybackRuntime",
    }
    workstation_key = created["LocalAudibleWorkstationRuntime"][1]["signing_key"]
    coordinator = created["LocalAudibleCoordinator"][1]
    assert len(
        {
            workstation_key,
            coordinator["signing_key"],
            coordinator["production_integrity_key"],
            coordinator["receipt_key"],
        }
    ) == 4


def test_module_has_no_paid_visual_or_provider_imports() -> None:
    tree = ast.parse(Path(runtime_module.__file__ or "").read_text())
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = ("krea", "provider", "gateway", "visual", "source_card")
    assert not any(token in name for name in imports for token in forbidden)
