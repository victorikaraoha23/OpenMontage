"""OpenMontage LTX-2.3 inference API on Modal.

Deploy from the repository root with:
    modal deploy docker/modal_ltx2/app.py

The endpoint is private-by-token. Model weights are cached in a Modal Volume;
HF_TOKEN must have access to the LTX-2.3 and Gemma 3 repositories.
"""
from __future__ import annotations

import base64
import hmac
import os
import subprocess
import tempfile
from pathlib import Path

import modal
from fastapi import Header, HTTPException

from service import validate_payload, download_reference_image

APP_NAME = "openmontage-ltx2"
MODEL_DIR = Path("/models")
CHECKPOINT_DIR = MODEL_DIR / "checkpoints"
GEMMA_DIR = MODEL_DIR / "gemma-3-12b-it"
LTX_REPO = "/opt/LTX-2"
LTX_REPO_COMMIT = "d151147788a9284cca791edc6ce898007e727fe6"

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name("openmontage-ltx2-models", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install("uv", "huggingface_hub", "fastapi[standard]", "requests", "pillow")
    .run_commands(
        f"git clone https://github.com/Lightricks/LTX-2.git {LTX_REPO}",
        f"cd {LTX_REPO} && git checkout {LTX_REPO_COMMIT}",
        f"cd {LTX_REPO} && uv sync --frozen",
    )
)

@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=1800,
    scaledown_window=300,
    volumes={"/models": model_volume},
    secrets=[modal.Secret.from_name("openmontage-ltx2")],
)
@modal.fastapi_endpoint(method="POST")
def generate(payload: dict, authorization: str = Header(default="")) -> dict:
    """Generate an MP4 and return it as base64 JSON for the OpenMontage client."""
    expected = os.environ.get("OPENMONTAGE_API_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token.")

    try:
        params = validate_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        raise HTTPException(status_code=503, detail="HF_TOKEN is not configured in the Modal secret.")

    try:
        from huggingface_hub import hf_hub_download, snapshot_download

        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint = hf_hub_download(
            repo_id="Lightricks/LTX-2.3",
            filename="ltx-2.3-22b-distilled-1.1.safetensors",
            token=hf_token,
            local_dir=str(CHECKPOINT_DIR),
        )
        upscaler = hf_hub_download(
            repo_id="Lightricks/LTX-2.3",
            filename="ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
            token=hf_token,
            local_dir=str(CHECKPOINT_DIR),
        )
        if not (GEMMA_DIR / "config.json").exists():
            snapshot_download(
                repo_id="google/gemma-3-12b-it",
                token=hf_token,
                local_dir=str(GEMMA_DIR),
            )
        model_volume.commit()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Model preparation failed: {type(exc).__name__}: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="openmontage-ltx2-") as temp_dir:
        temp = Path(temp_dir)
        output_path = temp / "generated.mp4"
        command = [
            "uv", "run", "--project", LTX_REPO, "--frozen", "python", "-m",
            "ltx_pipelines.distilled",
            "--distilled-checkpoint-path", checkpoint,
            "--gemma-root", str(GEMMA_DIR),
            "--spatial-upsampler-path", upscaler,
            "--prompt", params["prompt"],
            "--output-path", str(output_path),
            "--width", str(params["width"]),
            "--height", str(params["height"]),
            "--num-frames", str(params["num_frames"]),
            "--frame-rate", str(params["fps"]),
            "--seed", str(params["seed"]),
            "--quantization", os.environ.get("LTX_QUANTIZATION", "fp8-cast"),
        ]
        image_path = None
        if params.get("input_image"):
            image_path = temp / "reference-image"
            image_path.write_bytes(params["input_image"])
        elif params.get("input_image_url"):
            image_path = temp / "reference-image"
            try:
                download_reference_image(params["input_image_url"], image_path)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if image_path:
            command.extend(["--image", str(image_path), "0", "1.0"])

        try:
            result = subprocess.run(
                command, cwd=LTX_REPO, capture_output=True, text=True,
                timeout=1700, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="LTX generation exceeded the execution timeout.") from exc
        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            detail = (result.stderr or result.stdout or "LTX pipeline produced no output")[-6000:]
            raise HTTPException(status_code=500, detail=detail)

        video = output_path.read_bytes()
        return {
            "video_base64": base64.b64encode(video).decode("ascii"),
            "content_type": "video/mp4",
            "filename": "openmontage-ltx2.mp4",
            "width": params["width"],
            "height": params["height"],
            "num_frames": params["num_frames"],
            "fps": params["fps"],
            "seed": params["seed"],
            "model": "LTX-2.3-22B-Distilled-1.1",
        }
