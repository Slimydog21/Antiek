from __future__ import annotations

import ast
from pathlib import Path

import pytest

import interfaces.research.api.multimedia_local_runtime as runtime_module
from interfaces.research.api.multimedia_local_runtime import (
    multimedia_local_runtime_from_environment,
)
from substrate.multimedia.local_workstation import LocalWorkstationRuntime

PREFIX = "ANTIEK_MULTIMEDIA_LOCAL_"


def _environment(tmp_path: Path) -> dict[str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    directories = {}
    for name in (
        "TTS_OUTPUT_DIR", "CARD_OUTPUT_DIR", "NARRATION_OUTPUT_DIR",
        "VISUAL_OUTPUT_DIR", "RENDER_OUTPUT_DIR", "RECEIPT_OUTPUT_DIR",
    ):
        path = tmp_path / name.lower()
        path.mkdir(mode=0o700)
        directories[name] = str(path)
    resources = {}
    for name in ("FONT_PATH", "SAY_PATH", "FFMPEG_PATH", "FFPROBE_PATH"):
        path = tmp_path / name.lower()
        path.write_bytes(b"resource")
        path.chmod(0o755 if name != "FONT_PATH" else 0o600)
        resources[name] = str(path)
    names = (
        "WORKSTATION_KEY_HEX", "TTS_KEY_HEX", "CARD_KEY_HEX",
        "COORDINATOR_KEY_HEX", "NARRATION_KEY_HEX", "VISUAL_KEY_HEX",
        "EVIDENCE_KEY_HEX", "RENDER_KEY_HEX", "RECEIPT_KEY_HEX",
    )
    return {
        f"{PREFIX}ENABLED": "true",
        f"{PREFIX}DB_PATH": str(tmp_path / "local.duckdb"),
        f"{PREFIX}OPERATOR_SIGNING_KEY_HEX": (bytes([200]) * 32).hex(),
        f"{PREFIX}REVIEWER_IDS": "owner-1",
        f"{PREFIX}VOICE": "Samantha",
        f"{PREFIX}WORDS_PER_MINUTE": "180",
        f"{PREFIX}TIMEOUT_SECONDS": "300",
        **{
            f"{PREFIX}{name}": (bytes([index + 1]) * 32).hex()
            for index, name in enumerate(names)
        },
        **{f"{PREFIX}{name}": value for name, value in directories.items()},
        **{f"{PREFIX}{name}": value for name, value in resources.items()},
    }


def test_absent_is_none_and_partial_configuration_fails(tmp_path: Path) -> None:
    assert multimedia_local_runtime_from_environment(store=object(), environ={}) is None  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_local_runtime_from_environment(
            store=object(),  # type: ignore[arg-type]
            environ={f"{PREFIX}ENABLED": "true"},
        )
    values = _environment(tmp_path)
    values[f"{PREFIX}FFMPEG_PATH"] = ""
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_local_runtime_from_environment(store=object(), environ=values)  # type: ignore[arg-type]


def test_keys_must_be_independent_and_paths_private(tmp_path: Path) -> None:
    values = _environment(tmp_path)
    values[f"{PREFIX}TTS_KEY_HEX"] = values[f"{PREFIX}CARD_KEY_HEX"]
    with pytest.raises(RuntimeError, match="invalid"):
        multimedia_local_runtime_from_environment(store=object(), environ=values)  # type: ignore[arg-type]
    values = _environment(tmp_path / "second")
    Path(values[f"{PREFIX}VISUAL_OUTPUT_DIR"]).chmod(0o755)
    with pytest.raises(RuntimeError, match="directory"):
        multimedia_local_runtime_from_environment(store=object(), environ=values)  # type: ignore[arg-type]


def test_composes_only_local_authorities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = _environment(tmp_path)
    created: dict[str, object] = {}

    def capture(name):  # noqa: ANN001, ANN202
        def factory(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            result = object()
            created[name] = (args, kwargs, result)
            return result
        return factory

    for name in (
        "LocalTTSAdapter", "LocalSourceCardRegistry", "DiagramEvidenceAuthority",
        "LocalProductionCoordinator", "LocalVideoProductionCoordinator",
    ):
        monkeypatch.setattr(runtime_module, name, capture(name))
    result = multimedia_local_runtime_from_environment(
        store=object(), environ=values  # type: ignore[arg-type]
    )
    assert isinstance(result, LocalWorkstationRuntime)
    assert set(created) == {
        "LocalTTSAdapter", "LocalSourceCardRegistry", "DiagramEvidenceAuthority",
        "LocalProductionCoordinator", "LocalVideoProductionCoordinator",
    }
    assert result.signing_key != result.operator_signing_key


def test_module_has_no_paid_or_provider_runtime_imports() -> None:
    path = Path(runtime_module.__file__ or "")
    tree = ast.parse(path.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = ("krea", "provider", "gateway", "authorized_production", "reviewed_visual")
    assert not any(token in name for name in imports for token in forbidden)
