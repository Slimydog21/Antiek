"""HF GLM-5 checkpoint → TileRT shards on Modal Volume.

  modal run infrastructure/modal/tilert_glm5/prep_weights.py --hf-repo zai-org/GLM-5.2-FP8
"""

from __future__ import annotations

import os
import subprocess
import sys

import modal

APP_NAME = "antiek-tilert-glm5-prep"
WEIGHTS_VOL = modal.Volume.from_name("antiek-tilert-glm5-weights", create_if_missing=True)
HF_CACHE_VOL = modal.Volume.from_name("antiek-tilert-hf-cache", create_if_missing=True)

image = (
    modal.Image.from_registry("ghcr.io/tile-ai/tilert:cu132-latest")
    .pip_install("huggingface_hub>=0.35")
    .run_commands("pip install --no-cache-dir tilert==0.1.4")
    .env({"HF_HOME": "/hf-cache"})
)

app = modal.App(APP_NAME, image=image)


@app.function(
    gpu="B200:8",
    volumes={"/weights": WEIGHTS_VOL, "/hf-cache": HF_CACHE_VOL},
    secrets=[modal.Secret.from_name("antiek-hf-hub", required=False)],
    timeout=60 * 60 * 6,
)
def convert(hf_repo: str = "zai-org/GLM-5.2-FP8", revision: str | None = None):
    from huggingface_hub import snapshot_download

    # HuggingFace credential: Modal secret `antiek-hf-hub` → HF_TOKEN env (never literal).
    hub_credential = os.environ.get("HF_TOKEN")
    raw_dir = "/weights/hf-raw"
    out_dir = "/weights/glm5-tilert"
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    snapshot_download(
        repo_id=hf_repo,
        revision=revision,
        local_dir=raw_dir,
        token=hub_credential,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "tilert.models.preprocess.weight_converter",
            "--model_type",
            "glm-5",
            "--model_dir",
            raw_dir,
            "--save_dir",
            out_dir,
        ],
        check=True,
    )
    WEIGHTS_VOL.commit()
    return {"hf_repo": hf_repo, "tilert_dir": out_dir}


@app.local_entrypoint()
def main(hf_repo: str = "zai-org/GLM-5.2-FP8"):
    print(convert.remote(hf_repo))