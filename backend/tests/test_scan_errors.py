"""
Error UX: pipeline failures must map to the failure-handling contract, not
bare 500s. Retryable provider trouble (Anthropic 429/overload/connection,
Vision API errors) → 503 with Retry-After and a human message; timeouts →
504. The frontend surfaces `detail` on its error screen (Try Again +
report link), so the user never hits a dead end.
"""

import io

import httpx
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

from main import app
from app.services.detect_read_pipeline import DetectReadPipeline


client = TestClient(app)


def _jpeg_upload():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 30, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return {"image": ("test.jpg", buf, "image/jpeg")}


def _litellm_error(cls_name, status_code=None):
    import litellm
    cls = getattr(litellm.exceptions, cls_name)
    # litellm exception constructors need message/model/llm_provider.
    kwargs = dict(message="boom", model="anthropic/claude-sonnet-5",
                  llm_provider="anthropic")
    if cls_name == "Timeout":
        return cls(**kwargs)
    if status_code is not None:
        try:
            return cls(status_code=status_code, **kwargs)
        except TypeError:
            pass
    try:
        return cls(**kwargs)
    except TypeError:
        return cls("boom")


def _scan_raising(exc, monkeypatch):
    monkeypatch.setenv("PIPELINE_MODE", "detect_read")

    async def broken_scan(self, image_bytes, image_media_type="image/jpeg",
                          image_id=""):
        raise exc

    with patch.object(DetectReadPipeline, "scan", broken_scan):
        return client.post("/scan", files=_jpeg_upload())


class TestScanErrorMapping:
    def test_rate_limit_maps_to_503_with_retry_after(self, monkeypatch):
        response = _scan_raising(_litellm_error("RateLimitError"), monkeypatch)
        assert response.status_code == 503
        assert response.headers.get("Retry-After") is not None
        assert "try again" in response.json()["detail"].lower()

    def test_provider_overload_maps_to_503(self, monkeypatch):
        response = _scan_raising(
            _litellm_error("InternalServerError"), monkeypatch)
        assert response.status_code == 503

    def test_connection_error_maps_to_503(self, monkeypatch):
        response = _scan_raising(
            _litellm_error("APIConnectionError"), monkeypatch)
        assert response.status_code == 503

    def test_timeout_maps_to_504(self, monkeypatch):
        response = _scan_raising(_litellm_error("Timeout"), monkeypatch)
        assert response.status_code == 504
        assert "try again" in response.json()["detail"].lower()

    def test_vision_api_error_maps_to_503(self, monkeypatch):
        from google.api_core import exceptions as gexc
        response = _scan_raising(
            gexc.ServiceUnavailable("vision down"), monkeypatch)
        assert response.status_code == 503

    def test_unknown_error_stays_500(self, monkeypatch):
        response = _scan_raising(RuntimeError("who knows"), monkeypatch)
        assert response.status_code == 500


class TestScanStreamErrorMessage:
    def test_stream_error_event_carries_mapped_message(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_MODE", "detect_read")

        async def broken_stream(self, image_bytes, image_media_type="image/jpeg",
                                image_id=""):
            raise _litellm_error("RateLimitError")
            yield  # pragma: no cover — make this an async generator

        with patch.object(DetectReadPipeline, "scan_stream", broken_stream):
            response = client.post("/scan/stream", files=_jpeg_upload())

        assert response.status_code == 200
        assert "event: error" in response.text
        assert "try again" in response.text.lower()
