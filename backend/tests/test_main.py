"""Integration tests for the FastAPI app.

Gemini is mocked so these tests run without a real API key.
"""
import base64
import json
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import main as app_module
from main import app, _build_contents

client = TestClient(app)

# ── Tiny 1x1 white JPEG in base64 (for viewport tests) ───────────────────────
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
    "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
    "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAA"
    "AAAAAAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAAAAAA"
    "AAAA/9oADAMBAAIRAxEAPwCwABmX/9k="
)

VALID_PAYLOAD = {
    "telemetry": {
        "severity": "CRITICAL",
        "expected_latency_ms": 45,
        "delta_ms": 312,
        "diagnosis_category": "BGP_ROUTE_FLAP",
        "origin": "us-west-2",
        "destination": "eu-central-1",
        "affected_services": ["payment-gateway"],
        "timestamp": "2026-03-14T09:42:17Z",
    },
    "audience_type": "CTO",
}


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_body_schema(self):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert "version" in body


# ── /generate-briefing — input validation ─────────────────────────────────────

class TestGenerateBriefingValidation:
    def test_empty_telemetry_rejected(self):
        resp = client.post("/generate-briefing", json={"telemetry": {}, "audience_type": "CTO"})
        assert resp.status_code == 422

    def test_missing_telemetry_rejected(self):
        resp = client.post("/generate-briefing", json={"audience_type": "CTO"})
        assert resp.status_code == 422

    def test_invalid_audience_rejected(self):
        resp = client.post(
            "/generate-briefing",
            json={"telemetry": {"severity": "LOW"}, "audience_type": "ALIEN"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        # Pydantic wraps into a list of error dicts
        messages = " ".join(str(e) for e in detail)
        assert "audience_type" in messages

    def test_valid_audiences_accepted(self):
        """All five valid audience values should pass validation (not 422)."""
        for audience in ("CFO", "CTO", "CEO", "VP Engineering", "VP Finance"):
            fake_chunk = MagicMock()
            fake_chunk.text = "hello"

            with patch.object(app_module, "get_gemini_client") as mock_client:
                mock_genai = MagicMock()
                mock_genai.models.generate_content_stream.return_value = iter([fake_chunk])
                mock_client.return_value = mock_genai

                resp = client.post(
                    "/generate-briefing",
                    json={"telemetry": {"severity": "LOW"}, "audience_type": audience},
                )
                # Should stream (200), not reject (422)
                assert resp.status_code == 200, f"Failed for audience: {audience}"

    def test_audience_whitespace_stripped(self):
        """Audience with surrounding spaces should be normalised, not rejected."""
        fake_chunk = MagicMock()
        fake_chunk.text = "ok"

        with patch.object(app_module, "get_gemini_client") as mock_client:
            mock_genai = MagicMock()
            mock_genai.models.generate_content_stream.return_value = iter([fake_chunk])
            mock_client.return_value = mock_genai

            resp = client.post(
                "/generate-briefing",
                json={"telemetry": {"severity": "LOW"}, "audience_type": "  CTO  "},
            )
            assert resp.status_code == 200


# ── /generate-briefing — streaming output ────────────────────────────────────

def _collect_sse(response_text: str) -> list[dict]:
    """Parse raw SSE body into a list of decoded JSON event objects."""
    events = []
    for block in response_text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            raw = block[6:].strip()
            if raw:
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
    return events


def _make_text_chunk(text: str) -> MagicMock:
    """Build a mock Gemini chunk that has a text content part."""
    part = MagicMock()
    part.text = text
    part.inline_data = None
    candidate = MagicMock()
    candidate.content.parts = [part]
    chunk = MagicMock()
    chunk.candidates = [candidate]
    return chunk


class TestGenerateBriefingStream:
    def _mock_stream(self, texts: list[str]):
        """Return a context-manager that patches get_gemini_client to yield given texts."""
        chunks = [_make_text_chunk(t) for t in texts]

        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = iter(chunks)
        return patch.object(app_module, "get_gemini_client", return_value=mock_client)

    def test_stream_starts_with_start_event(self):
        with self._mock_stream(["hello"]):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        assert events[0]["type"] == "start"

    def test_stream_ends_with_end_event(self):
        with self._mock_stream(["some text"]):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        assert events[-1]["type"] == "end"

    def test_chunk_events_carry_text(self):
        with self._mock_stream(["Frame 1", " content"]):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        chunk_texts = [e["text"] for e in events if e["type"] == "chunk"]
        assert "Frame 1" in chunk_texts
        assert " content" in chunk_texts

    def test_empty_chunk_text_not_emitted(self):
        """Chunks with no text (e.g. metadata-only Gemini responses) are silently dropped."""
        chunks = [
            # empty part — no text, no inline_data
            MagicMock(candidates=[]),
            # text part with empty string — should be dropped
            _make_text_chunk(""),
            # real text part
            _make_text_chunk("real"),
        ]
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = iter(chunks)
        with patch.object(app_module, "get_gemini_client", return_value=mock_client):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        chunk_events = [e for e in _collect_sse(resp.text) if e["type"] == "chunk"]
        assert all(e["text"] for e in chunk_events)
        assert len(chunk_events) == 1

    def test_gemini_error_yields_error_event(self):
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.side_effect = RuntimeError("quota exceeded")
        with patch.object(app_module, "get_gemini_client", return_value=mock_client):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        error_events = [e for e in events if e["type"] == "error"]
        assert error_events
        assert "quota exceeded" in error_events[0]["message"]

    def test_content_type_is_event_stream(self):
        with self._mock_stream(["x"]):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        assert "text/event-stream" in resp.headers["content-type"]

    def test_cache_control_no_cache(self):
        with self._mock_stream(["x"]):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        assert resp.headers.get("cache-control") == "no-cache"


# ── Gemini client singleton ───────────────────────────────────────────────────

class TestGeminiClientSingleton:
    def test_same_instance_returned(self):
        # Reset cached singleton first
        app_module._gemini_client = None
        with patch("main.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            c1 = app_module.get_gemini_client()
            c2 = app_module.get_gemini_client()
        assert c1 is c2
        assert mock_cls.call_count == 1

    def test_missing_api_key_raises(self):
        app_module._gemini_client = None
        original = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
                app_module.get_gemini_client()
        finally:
            if original:
                os.environ["GEMINI_API_KEY"] = original
            app_module._gemini_client = None


# ── ViewportImage validation ──────────────────────────────────────────────────

class TestViewportImageValidation:
    def test_valid_base64_accepted(self):
        resp = client.post(
            "/generate-briefing",
            json={
                **VALID_PAYLOAD,
                "viewport_image": {"mime_type": "image/jpeg", "data": TINY_JPEG_B64},
            },
        )
        # Passes validation (Gemini is not called in real, but no 422)
        assert resp.status_code != 422

    def test_invalid_base64_rejected(self):
        resp = client.post(
            "/generate-briefing",
            json={
                **VALID_PAYLOAD,
                "viewport_image": {"mime_type": "image/jpeg", "data": "!!!not-base64!!!"},
            },
        )
        assert resp.status_code == 422
        detail = str(resp.json()["detail"])
        assert "base64" in detail.lower()

    def test_viewport_image_optional(self):
        """Omitting viewport_image entirely should not raise."""
        payload_no_viewport = {k: v for k, v in VALID_PAYLOAD.items()}
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = iter([MagicMock(candidates=[])])
        with patch.object(app_module, "get_gemini_client", return_value=mock_client):
            resp = client.post("/generate-briefing", json=payload_no_viewport)
        assert resp.status_code == 200


# ── _build_contents ───────────────────────────────────────────────────────────

class TestBuildContents:
    def test_no_viewport_returns_string(self):
        result = _build_contents("hello", None)
        assert result == "hello"

    def test_with_viewport_returns_list(self):
        from main import ViewportImage
        vp = ViewportImage(mime_type="image/jpeg", data=TINY_JPEG_B64)
        result = _build_contents("hello", vp)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_viewport_list_has_image_part_first(self):
        from main import ViewportImage
        from google.genai import types
        vp = ViewportImage(mime_type="image/jpeg", data=TINY_JPEG_B64)
        result = _build_contents("msg", vp)
        # First part should be bytes (image), second should be text
        assert result[0].inline_data is not None
        assert result[1].text == "msg"


# ── Native audio SSE events ───────────────────────────────────────────────────

class TestNativeAudioStream:
    """Verify audio parts from Gemini produce 'audio' SSE events."""

    def _make_audio_chunk(self, pcm_bytes: bytes = b"\x00\x01" * 100) -> MagicMock:
        """Build a mock Gemini chunk that has an audio inline_data part."""
        part = MagicMock()
        part.text = None
        part.inline_data = MagicMock()
        part.inline_data.mime_type = "audio/pcm;rate=24000"
        part.inline_data.data = pcm_bytes

        candidate = MagicMock()
        candidate.content.parts = [part]

        chunk = MagicMock()
        chunk.candidates = [candidate]
        return chunk

    def test_audio_chunk_emits_audio_event(self):
        chunks = [self._make_audio_chunk(), MagicMock(candidates=[])]
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = iter(chunks)
        with patch.object(app_module, "get_gemini_client", return_value=mock_client):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        audio_events = [e for e in events if e["type"] == "audio"]
        assert audio_events
        assert audio_events[0]["mime_type"] == "audio/pcm;rate=24000"
        # data field should be valid base64
        base64.b64decode(audio_events[0]["data"])

    def test_audio_event_data_roundtrips(self):
        """The PCM bytes should survive base64 encode→SSE→decode intact."""
        pcm = bytes(range(256)) * 4
        chunks = [self._make_audio_chunk(pcm), MagicMock(candidates=[])]
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = iter(chunks)
        with patch.object(app_module, "get_gemini_client", return_value=mock_client):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        audio_events = [e for e in events if e["type"] == "audio"]
        decoded = base64.b64decode(audio_events[0]["data"])
        assert decoded == pcm

    def test_interleaved_text_and_audio(self):
        """Text and audio chunks can appear in any order; both should be emitted."""
        chunks = [
            _make_text_chunk("[Frame 1"),
            self._make_audio_chunk(),
            _make_text_chunk("] intro"),
            MagicMock(candidates=[]),
        ]
        mock_client = MagicMock()
        mock_client.models.generate_content_stream.return_value = iter(chunks)
        with patch.object(app_module, "get_gemini_client", return_value=mock_client):
            resp = client.post("/generate-briefing", json=VALID_PAYLOAD)
        events = _collect_sse(resp.text)
        types_seen = {e["type"] for e in events}
        assert "chunk" in types_seen
        assert "audio" in types_seen
