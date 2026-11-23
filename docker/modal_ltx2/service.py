"""Pure validation and safe reference-image download helpers for the Modal API."""
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PROMPT_CHARS = 2000


def validate_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"prompt must contain 1-{MAX_PROMPT_CHARS} characters.")
    width = _integer(payload.get("width", 576), "width")
    height = _integer(payload.get("height", 1024), "height")
    if width < 256 or height < 256 or width > 1280 or height > 1280:
        raise ValueError("width and height must be between 256 and 1280.")
    if width % 64 or height % 64:
        raise ValueError("width and height must be multiples of 64 for this LTX pipeline.")
    if width * height > 1280 * 1024:
        raise ValueError("Requested pixel count exceeds the configured limit.")
    frames = _integer(payload.get("num_frames", 121), "num_frames")
    if frames < 25 or frames > 193 or (frames - 1) % 8:
        raise ValueError("num_frames must be 25..193 and satisfy (num_frames - 1) % 8 == 0.")
    fps = _integer(payload.get("fps", 24), "fps")
    if fps < 1 or fps > 60:
        raise ValueError("fps must be between 1 and 60.")
    seed = _integer(payload.get("seed", 42), "seed")
    image_b64 = payload.get("input_image")
    if image_b64 is not None:
        if not isinstance(image_b64, str):
            raise ValueError("input_image must be a base64 string.")
        import base64
        import binascii
        try:
            image_bytes = base64.b64decode(image_b64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("input_image is not valid base64.") from exc
        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("input_image must be non-empty and no larger than 20 MiB.")
    else:
        image_bytes = None
    image_url = payload.get("input_image_url")
    if image_url is not None and image_bytes is not None:
        raise ValueError("Provide input_image or input_image_url, not both.")
    if image_url is not None and not isinstance(image_url, str):
        raise ValueError("input_image_url must be a URL string.")
    return {
        "prompt": prompt.strip(), "width": width, "height": height,
        "num_frames": frames, "fps": fps, "seed": seed,
        "input_image": image_bytes, "input_image_url": image_url,
    }


def _integer(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if isinstance(value, float) and value != result:
        raise ValueError(f"{field} must be an integer.")
    return result


def download_reference_image(url: str, destination: Path) -> None:
    """Fetch HTTPS images only from public IPs; refuse redirects and oversized bodies."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Reference image URL must be an HTTPS URL without embedded credentials.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Reference image host could not be resolved.") from exc
    if not addresses:
        raise ValueError("Reference image host did not resolve.")
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("Reference image URL must resolve only to public IP addresses.")
    import requests
    response = None
    try:
        response = requests.get(url, timeout=30, allow_redirects=False, stream=True)
        if 300 <= response.status_code < 400:
            raise ValueError("Reference image redirects are not allowed.")
        response.raise_for_status()
        length = response.headers.get("content-length")
        if length and int(length) > MAX_IMAGE_BYTES:
            raise ValueError("Reference image exceeds the 20 MiB limit.")
        total = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise ValueError("Reference image exceeds the 20 MiB limit.")
                handle.write(chunk)
    except requests.RequestException as exc:
        raise ValueError(f"Reference image download failed: {exc}") from exc
    finally:
        if response is not None:
            response.close()
    try:
        from PIL import Image
        with Image.open(destination) as image:
            image.verify()
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise ValueError("Reference image is not a valid supported image.") from exc
