"""
Tests for POST /scan/stream — progressive scan via Server-Sent Events.

Contract: each `partial` event and the single terminal `done` event carry a
complete ScanResponse JSON (cumulative replacement — the frontend swaps its
whole state). A pipeline failure after streaming has begun emits an `error`
event. Only PIPELINE_MODE=detect_read supports streaming; other modes get 501
so clients fall back to POST /scan.
"""

import io
import json

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

from main import app
from app.services.detect_read_pipeline import DetectReadPipeline
from app.services.single_llm_pipeline import SingleLLMResult


client = TestClient(app)


def _jpeg_upload():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 30, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return {"image": ("test.jpg", buf, "image/jpeg")}


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event:
            events.append((event, data))
    return events


class TestScanStreamEndpoint:
    def test_emits_partial_then_done(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_MODE", "detect_read")

        async def fake_stream(self, image_bytes, image_media_type="image/jpeg",
                              image_id=""):
            yield SingleLLMResult(recognized_wines=[], raw_llm_wines=[],
                                  timings={"partial_ms": 1}, partial=True)
            yield SingleLLMResult(recognized_wines=[], raw_llm_wines=[],
                                  timings={"total_ms": 2})

        with patch.object(DetectReadPipeline, "scan_stream", fake_stream):
            response = client.post("/scan/stream", files=_jpeg_upload())

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.text)
        assert [e[0] for e in events] == ["partial", "done"]
        # Every event carries a complete ScanResponse.
        for _, data in events:
            assert set(data) >= {"image_id", "results", "fallback_list"}
        # Same scan id across events.
        assert events[0][1]["image_id"] == events[1][1]["image_id"]

    def test_pipeline_failure_emits_error_event(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_MODE", "detect_read")

        async def broken_stream(self, image_bytes, image_media_type="image/jpeg",
                                image_id=""):
            yield SingleLLMResult(recognized_wines=[], raw_llm_wines=[],
                                  timings={"partial_ms": 1}, partial=True)
            raise RuntimeError("provider exploded")

        with patch.object(DetectReadPipeline, "scan_stream", broken_stream):
            response = client.post("/scan/stream", files=_jpeg_upload())

        assert response.status_code == 200  # already streaming
        events = _parse_sse(response.text)
        assert events[-1][0] == "error"
        assert "message" in events[-1][1]

    def test_non_detect_read_mode_returns_501(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_MODE", "single_llm")
        response = client.post("/scan/stream", files=_jpeg_upload())
        assert response.status_code == 501

    def test_invalid_content_type_rejected(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_MODE", "detect_read")
        response = client.post(
            "/scan/stream",
            files={"image": ("t.txt", io.BytesIO(b"nope"), "text/plain")},
        )
        assert response.status_code == 400
