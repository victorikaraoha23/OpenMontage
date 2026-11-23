from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "modal_ltx2"))
from service import validate_payload


def test_vertical_default_payload():
    result = validate_payload({"prompt": "A clean cinematic product shot"})
    assert (result["width"], result["height"]) == (576, 1024)
    assert result["num_frames"] == 121
    assert result["fps"] == 24


def test_valid_image_payload():
    result = validate_payload({"prompt": "Animate this", "input_image": "aGVsbG8="})
    assert result["input_image"] == b"hello"


def test_rejects_invalid_frame_grid():
    try:
        validate_payload({"prompt": "test", "num_frames": 120})
    except ValueError as exc:
        assert "num_frames" in str(exc)
    else:
        raise AssertionError("Invalid frame count was accepted")


def test_rejects_unsupported_resolution():
    try:
        validate_payload({"prompt": "test", "width": 500, "height": 1024})
    except ValueError as exc:
        assert "multiples of 64" in str(exc)
    else:
        raise AssertionError("Invalid resolution was accepted")


def test_rejects_bad_base64():
    try:
        validate_payload({"prompt": "test", "input_image": "not base64!"})
    except ValueError as exc:
        assert "base64" in str(exc)
    else:
        raise AssertionError("Invalid base64 was accepted")
