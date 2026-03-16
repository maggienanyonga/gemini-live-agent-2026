"""Tests for the Phase 1 /ws WebSocket endpoint (Latency Lens live session).

Mirrors test_cs_websocket.py but covers /ws-specific behaviour:
- Response key is "data" (not "content") for text messages
- Accepts "video" messages (not "frame") for screen share
- No action-tag stripping (LL doesn't use [ACTION:] tags)
"""
import asyncio
import base64
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import main as app_module
from main import app

client = TestClient(app)


# ── Fake session (reused from cs-ws tests pattern) ───────────────────────────

class _FakeAsyncIter:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            await asyncio.sleep(0)
            raise StopAsyncIteration


class _FakeTurn:
    def __init__(self, responses):
        self._responses = responses

    def __aiter__(self):
        return _FakeAsyncIter(self._responses)


class _FakeSession:
    def __init__(self, turns):
        self._turns = list(turns)
        self._idx = 0
        self.sent = []

    async def send_realtime_input(self, **kwargs):
        self.sent.append(kwargs)

    async def send(self, input=None, end_of_turn=False):
        self.sent.append({"input": input, "end_of_turn": end_of_turn})

    def receive(self):
        if self._idx < len(self._turns):
            turn = self._turns[self._idx]
            self._idx += 1
            return _FakeTurn(turn)
        return _FakeTurn([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


def _patch_ll(session):
    mock_ll = MagicMock()
    mock_ll.aio.live.connect.return_value = session
    return patch.object(app_module, "get_ll_client", return_value=mock_ll)


def _text_resp(text):
    r = MagicMock()
    r.text = text
    r.data = None
    r.server_content = None
    return r


def _audio_resp(pcm=b"\x00\x01" * 50):
    r = MagicMock()
    r.text = None
    r.data = pcm
    r.server_content = None
    return r


def _interrupted_resp():
    r = MagicMock()
    r.text = None
    r.data = None
    sc = MagicMock()
    sc.interrupted = True
    r.server_content = sc
    return r


# ── Connection ────────────────────────────────────────────────────────────────

class TestLLWebSocketConnection:
    def test_endpoint_accepts_websocket(self):
        with _patch_ll(_FakeSession([])):
            with client.websocket_connect("/ws") as ws:
                ws.close()

    def test_http_get_returns_404(self):
        resp = client.get("/ws")
        assert resp.status_code == 404


# ── Text output ───────────────────────────────────────────────────────────────

class TestLLTextOutput:
    def test_text_event_emitted(self):
        with _patch_ll(_FakeSession([[_text_resp("Scanning route.")]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "text"

    def test_text_uses_data_key_not_content(self):
        """Phase 1 uses 'data' key; Phase 3 uses 'content'. They must not be confused."""
        with _patch_ll(_FakeSession([[_text_resp("hello")]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert "data" in msg
        assert "content" not in msg

    def test_text_value_correct(self):
        with _patch_ll(_FakeSession([[_text_resp("BGP flap detected.")]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["data"] == "BGP flap detected."

    def test_action_tags_not_stripped(self):
        """Phase 1 does NOT parse action tags — raw text flows through."""
        raw = "Stitching route.\n[ACTION: CLICK_SAVE]\nDone."
        with _patch_ll(_FakeSession([[_text_resp(raw)]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "text"
        # Action tag NOT stripped (unlike cs-ws)
        assert "[ACTION:" in msg["data"]


# ── Audio output ──────────────────────────────────────────────────────────────

class TestLLAudioOutput:
    def test_audio_event_emitted(self):
        with _patch_ll(_FakeSession([[_audio_resp()]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "audio"

    def test_audio_data_valid_base64(self):
        with _patch_ll(_FakeSession([[_audio_resp()]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        base64.b64decode(msg["data"])  # must not raise

    def test_audio_data_roundtrips(self):
        pcm = bytes(range(256))
        with _patch_ll(_FakeSession([[_audio_resp(pcm)]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert base64.b64decode(msg["data"]) == pcm


# ── Interrupted ───────────────────────────────────────────────────────────────

class TestLLInterrupted:
    def test_interrupted_event_emitted(self):
        with _patch_ll(_FakeSession([[_interrupted_resp()]])):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "interrupted"


# ── Browser → Gemini ─────────────────────────────────────────────────────────

class TestLLBrowserToGemini:
    def _send_and_close(self, payload):
        with _patch_ll(_FakeSession([])):
            with client.websocket_connect("/ws") as ws:
                ws.send_json(payload)
                ws.close()

    def test_audio_message_does_not_crash(self):
        self._send_and_close({"type": "audio", "data": base64.b64encode(b"\x01\x02").decode()})

    def test_video_message_does_not_crash(self):
        """Phase 1 uses 'video' type for screen share (Phase 3 uses 'frame')."""
        self._send_and_close({"type": "video", "data": base64.b64encode(b"\xff\xd8" + b"\x00" * 10).decode()})

    def test_missing_data_silently_skipped(self):
        self._send_and_close({"type": "audio"})  # no "data" key

    def test_unknown_type_silently_skipped(self):
        self._send_and_close({"type": "unknown_type", "data": "abc"})


# ── Error handling ────────────────────────────────────────────────────────────

class TestLLErrorHandling:
    def test_live_connect_failure_emits_error(self):
        mock_ll = MagicMock()
        mock_ll.aio.live.connect.side_effect = RuntimeError("v1beta unavailable")
        with patch.object(app_module, "get_ll_client", return_value=mock_ll):
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "error"
        assert "v1beta unavailable" in msg["message"]

    def test_interleaved_text_and_audio_both_delivered(self):
        responses = [_text_resp("Route analysis"), _audio_resp()]
        with _patch_ll(_FakeSession([responses])):
            with client.websocket_connect("/ws") as ws:
                e1 = ws.receive_json()
                e2 = ws.receive_json()
                ws.close()
        assert {e1["type"], e2["type"]} == {"text", "audio"}
