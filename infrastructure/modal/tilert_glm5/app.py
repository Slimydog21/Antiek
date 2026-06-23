"""TileRT GLM-5 on Modal — OpenAI-compat surface for Antiek dispatch.

Deploy from repo root:
  modal deploy infrastructure/modal/tilert_glm5/app.py

Secrets:
  modal secret create antiek-tilert-auth \\
    ANTIEK_TILERT_MODAL_TOKEN=$(openssl rand -hex 32)
"""

from __future__ import annotations

import os
import secrets
import sys
import threading
from pathlib import Path
from typing import Any

import modal

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from openai_shim import handle_chat_completions  # noqa: E402

APP_NAME = "antiek-tilert-glm5"
WEIGHTS_MOUNT = "/weights/glm5-tilert"
DEFAULT_MODEL_ID = os.environ.get("TILERT_MODEL_ID", "glm5")
WEIGHTS_VOL = modal.Volume.from_name("antiek-tilert-glm5-weights", create_if_missing=True)

image = (
    modal.Image.from_registry("ghcr.io/tile-ai/tilert:cu132-latest")
    .pip_install("fastapi[standard]>=0.115", "huggingface_hub>=0.35")
    .run_commands("pip install --no-cache-dir tilert==0.1.4")
    .add_local_dir(_HERE, remote_path="/opt/tilert_glm5")
)

auth_secret = modal.Secret.from_name("antiek-tilert-auth")
app = modal.App(APP_NAME, image=image)


@app.cls(
    image=image,
    gpu="B200:8",
    secrets=[auth_secret],
    volumes={WEIGHTS_MOUNT: WEIGHTS_VOL},
    timeout=60 * 30,
    scaledown_window=600,
    min_containers=int(os.environ.get("TILERT_MIN_CONTAINERS", "0")),
    max_containers=1,
)
@modal.concurrent(max_inputs=1)
class TileRTGLM5Service:
    _lock: threading.Lock
    _generator: Any

    @modal.enter()
    def load(self):
        sys.path.insert(0, "/opt/tilert_glm5")
        import tilert
        from tilert.models.glm_5.generator import GLM5Generator
        from tilert.models.glm_5.model_args import ModelArgs

        self._lock = threading.Lock()
        with_mtp = os.environ.get("TILERT_WITH_MTP", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        weights_dir = os.environ.get("TILERT_WEIGHTS_DIR", WEIGHTS_MOUNT)
        if not os.path.isdir(weights_dir):
            raise RuntimeError(
                f"TileRT weights missing at {weights_dir}. "
                "Run: modal run infrastructure/modal/tilert_glm5/prep_weights.py"
            )

        tilert.load_backend("glm5")
        self._generator = GLM5Generator(
            model_args=ModelArgs(),
            max_new_tokens=4096,
            model_weights_dir=weights_dir,
            with_mtp=with_mtp,
        )
        self._generator.from_pretrained()

    def _generate_locked(self, prompt: str, max_new_tokens: int) -> str:
        with self._lock:
            prev = getattr(self._generator, "max_new_tokens", None)
            if prev is not None:
                self._generator.max_new_tokens = max_new_tokens
            try:
                return str(self._generator.generate(prompt))
            finally:
                if prev is not None:
                    self._generator.max_new_tokens = prev

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse

        service = self
        api = FastAPI(title="Antiek TileRT GLM-5", docs_url=None, redoc_url=None)

        def _check_bearer(request: Request) -> None:
            expected = os.environ.get("ANTIEK_TILERT_MODAL_TOKEN", "")
            if not expected:
                raise HTTPException(status_code=503, detail="auth not configured")
            header = request.headers.get("authorization", "")
            if not header.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="unauthorized")
            token = header.removeprefix("Bearer ")
            if not secrets.compare_digest(token, expected):
                raise HTTPException(status_code=401, detail="unauthorized")

        @api.get("/health")
        async def health():
            return {"status": "ok", "backend": "tilert-glm5", "model": DEFAULT_MODEL_ID}

        @api.get("/v1/models")
        async def list_models(request: Request):
            _check_bearer(request)
            return {
                "object": "list",
                "data": [
                    {"id": DEFAULT_MODEL_ID, "object": "model", "owned_by": "tilert"},
                ],
            }

        @api.post("/v1/chat/completions")
        async def chat(request: Request):
            _check_bearer(request)
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="body must be object")

            try:
                payload = handle_chat_completions(
                    body,
                    generate=service._generate_locked,
                    default_model=DEFAULT_MODEL_ID,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return JSONResponse(payload)

        return api