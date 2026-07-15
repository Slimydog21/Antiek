from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from interfaces.research.api import multimedia_routes as multimedia_routes_module
from interfaces.research.api.multimedia_production_worker_routes import (
    get_multimedia_production_worker_runtime,
)
from interfaces.research.api.multimedia_production_worker_runtime import (
    multimedia_production_worker_runtime_from_environment,
)
from substrate.multimedia.diagram_evidence_authority import DiagramEvidenceAuthority
from substrate.multimedia.read_model import MultimediaAssetStore


def _configuration(tmp_path: Path) -> dict[str, str]:
    root = tmp_path.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    dirs = {}
    for name in ("narration", "visual", "render", "receipt"):
        path = root / name
        path.mkdir(mode=0o700)
        dirs[name] = str(path)
    binaries = {}
    for name in ("ffmpeg", "ffprobe"):
        path = root / name
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o700)
        binaries[name] = str(path)
    prefix = "ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_"
    return {
        f"{prefix}ENABLED": "true",
        f"{prefix}DB_PATH": str(root / "production.duckdb"),
        f"{prefix}SIGNING_KEY_HEX": "01" * 32,
        f"{prefix}NARRATION_KEY_HEX": "02" * 32,
        f"{prefix}VISUAL_KEY_HEX": "03" * 32,
        f"{prefix}EVIDENCE_KEY_HEX": "04" * 32,
        f"{prefix}RENDER_KEY_HEX": "05" * 32,
        f"{prefix}RECEIPT_KEY_HEX": "06" * 32,
        f"{prefix}NARRATION_OUTPUT_DIR": dirs["narration"],
        f"{prefix}VISUAL_OUTPUT_DIR": dirs["visual"],
        f"{prefix}RENDER_OUTPUT_DIR": dirs["render"],
        f"{prefix}RECEIPT_OUTPUT_DIR": dirs["receipt"],
        f"{prefix}REVIEWED_VISUAL_DB_PATH": str(root / "visuals.duckdb"),
        f"{prefix}REVIEWED_VISUAL_KEY_HEX": "07" * 32,
        f"{prefix}VISUAL_EVIDENCE_DB_PATH": str(root / "evidence.duckdb"),
        f"{prefix}VISUAL_OPERATOR_VERIFY_KEY_HEX": "08" * 32,
        f"{prefix}VISUAL_REVIEWER_IDS": "reviewer-1,reviewer-2",
        f"{prefix}TTS_GATEWAY_URL": "https://tts.example.test/v1/synthesize",
        f"{prefix}TTS_GATEWAY_TOKEN": "gateway-secret",
        f"{prefix}TTS_ACCOUNT_IDENTITY_DIGEST": "a" * 64,
        f"{prefix}TTS_GATEWAY_TIMEOUT_SECONDS": "30",
        f"{prefix}FFMPEG_PATH": binaries["ffmpeg"],
        f"{prefix}FFPROBE_PATH": binaries["ffprobe"],
        f"{prefix}WIDTH_PX": "1280",
        f"{prefix}HEIGHT_PX": "720",
        f"{prefix}FPS": "30",
        f"{prefix}TIMEOUT_SECONDS": "300",
    }


def test_empty_disables_and_complete_configuration_composes_exact_runtime(tmp_path: Path) -> None:
    store = MultimediaAssetStore(str(tmp_path / "store"))
    assert multimedia_production_worker_runtime_from_environment(
        store=store, environ={}
    ) is None
    runtime = multimedia_production_worker_runtime_from_environment(
        store=store,
        environ=_configuration(tmp_path / "runtime"),
        gateway_poster=lambda *_args: pytest.fail("gateway must remain lazy"),
    )
    assert runtime is not None
    assert runtime.store is store
    assert runtime.playback.receipt_root == str((tmp_path / "runtime" / "receipt").resolve())
    assert runtime.receipt_output_dir == runtime.playback.receipt_root
    assert runtime.signing_key == bytes.fromhex("01" * 32)
    assert runtime.narration_integrity_key == runtime.playback.narration_key
    assert runtime.visual_integrity_key == runtime.playback.visual_key
    assert runtime.render_integrity_key == runtime.playback.render_key
    assert runtime.receipt_key == runtime.playback.receipt_key
    assert runtime.width_px == 1280
    assert runtime.height_px == 720
    assert runtime.fps == 30
    assert isinstance(runtime.verify_evidence, DiagramEvidenceAuthority)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("SIGNING_KEY_HEX", "00", "invalid"),
        ("VISUAL_OPERATOR_VERIFY_KEY_HEX", "00", "invalid"),
        ("TTS_GATEWAY_URL", "http://tts.example.test", "HTTPS"),
        ("WIDTH_PX", "99999", "invalid"),
        ("TTS_GATEWAY_TIMEOUT_SECONDS", "0", "between"),
    ],
)
def test_malformed_configuration_fails_startup(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    store = MultimediaAssetStore(str(tmp_path / "store"))
    config = _configuration(tmp_path / "runtime")
    config[f"ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_{field}"] = value
    with pytest.raises((RuntimeError, ValueError), match=message):
        multimedia_production_worker_runtime_from_environment(store=store, environ=config)


def test_partial_and_nonprivate_root_fail_startup(tmp_path: Path) -> None:
    store = MultimediaAssetStore(str(tmp_path / "store"))
    config = _configuration(tmp_path / "runtime")
    config.pop("ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_RECEIPT_KEY_HEX")
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_production_worker_runtime_from_environment(store=store, environ=config)

    config = _configuration(tmp_path / "runtime-2")
    Path(config["ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_VISUAL_OUTPUT_DIR"]).chmod(0o755)
    with pytest.raises(RuntimeError, match="private directory"):
        multimedia_production_worker_runtime_from_environment(store=store, environ=config)

    config = _configuration(tmp_path / "runtime-3")
    config["ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_RECEIPT_KEY_HEX"] = config[
        "ANTIEK_MULTIMEDIA_PRODUCTION_WORKER_RENDER_KEY_HEX"
    ]
    with pytest.raises(RuntimeError, match="independent"):
        multimedia_production_worker_runtime_from_environment(store=store, environ=config)


def test_app_registration_installs_composed_runtime(tmp_path: Path, monkeypatch) -> None:
    store = MultimediaAssetStore(str(tmp_path / "store"))
    runtime = multimedia_production_worker_runtime_from_environment(
        store=store,
        environ=_configuration(tmp_path / "runtime"),
        gateway_poster=lambda *_args: pytest.fail("gateway must remain lazy"),
    )
    assert runtime is not None
    assert "signing_key" not in repr(runtime)
    assert "010101" not in repr(runtime)
    monkeypatch.setattr(multimedia_routes_module, "_STORE", store)
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_reconciliation_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_knowledge_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module, "multimedia_playback_runtime_from_environment", lambda: None
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_narration_authorization_runtime_from_environment",
        lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_reviewed_visual_runtime_from_environment",
        lambda *, store: None,
    )
    monkeypatch.setattr(
        multimedia_routes_module,
        "multimedia_production_worker_runtime_from_environment",
        lambda *, store: runtime,
    )
    app = FastAPI()
    multimedia_routes_module.register_multimedia_routes(app)
    assert app.dependency_overrides[get_multimedia_production_worker_runtime]() is runtime
