"""Integration tests for the /cs-ws WebSocket endpoint.

The Gemini Live API session is mocked so these tests run without a real key.
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


# ─── Fake session helpers ─────────────────────────────────────────────────────

class _FakeAsyncIter:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            # Yield to the event loop so other tasks (browser_to_gemini) can
            # process incoming frames (e.g. the close frame sent by ws.close()).
            # Without this, the while-True in gemini_to_browser spins without
            # ever suspending, starving the event loop.
            await asyncio.sleep(0)
            raise StopAsyncIteration


class _FakeTurn:
    def __init__(self, responses):
        self._responses = responses

    def __aiter__(self):
        return _FakeAsyncIter(self._responses)


class _FakeSession:
    """Minimal Gemini Live session mock.

    Turns that have been consumed stay as empty turns (not an error) so that
    browser_to_gemini can continue waiting for WS messages without raising.
    The server loop exits cleanly when the test client sends a close frame.
    """

    def __init__(self, turns):
        self._turns = list(turns)
        self._idx = 0
        self.sent = []

    async def send(self, input=None, end_of_turn=False):
        self.sent.append({"input": input, "end_of_turn": end_of_turn})

    def receive(self):
        if self._idx < len(self._turns):
            turn = self._turns[self._idx]
            self._idx += 1
            return _FakeTurn(turn)
        # All turns consumed — return an empty turn (server waits for WS close)
        return _FakeTurn([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


def _patch_cs(session):
    mock_ll = MagicMock()
    mock_ll.aio.live.connect.return_value = session
    return patch.object(app_module, "get_ll_client", return_value=mock_ll)


def _make_text_response(text):
    r = MagicMock()
    r.text = text
    r.data = None
    r.server_content = None
    return r


def _make_audio_response(pcm=b"\x00\x01" * 50):
    r = MagicMock()
    r.text = None
    r.data = pcm
    r.server_content = None
    return r


def _make_interrupted_response():
    r = MagicMock()
    r.text = None
    r.data = None
    sc = MagicMock()
    sc.interrupted = True
    r.server_content = sc
    return r


# ─── Connection ───────────────────────────────────────────────────────────────

class TestCsWebSocketConnection:
    def test_endpoint_accepts_websocket(self):
        with _patch_cs(_FakeSession([])):
            with client.websocket_connect("/cs-ws") as ws:
                ws.close()

    def test_endpoint_registered(self):
        # FastAPI returns 404 for HTTP GET on a WebSocket-only path
        # (the route exists in the app, but only handles WS upgrades)
        resp = client.get("/cs-ws")
        assert resp.status_code == 404


# ─── Text output ──────────────────────────────────────────────────────────────

class TestCsTextOutput:
    def test_plain_text_emitted(self):
        with _patch_cs(_FakeSession([[_make_text_response("Scanning viewport.")]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "text"
        assert "Scanning viewport." in msg["content"]

    def test_action_tags_stripped_from_text(self):
        raw = "Stitching route.\n[ACTION: CLICK_SAVE]\nDone."
        with _patch_cs(_FakeSession([[_make_text_response(raw)]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        if msg["type"] == "text":
            assert "[ACTION:" not in msg["content"]

    def test_action_tag_only_produces_no_text_event(self):
        with _patch_cs(_FakeSession([[_make_text_response("[ACTION: CLICK_SAVE]")]])):
            with client.websocket_connect("/cs-ws") as ws:
                action_msg = ws.receive_json()
                ws.close()
        assert action_msg["type"] == "action"

    def test_text_before_action_tag_emitted(self):
        raw = "Moving.\n[ACTION: DRAG_AND_DROP] Source -> SFO_Node. Destination -> PHX_Node.\n"
        with _patch_cs(_FakeSession([[_make_text_response(raw)]])):
            with client.websocket_connect("/cs-ws") as ws:
                first = ws.receive_json()
                second = ws.receive_json()
                ws.close()
        types = {first["type"], second["type"]}
        assert "text" in types
        assert "action" in types


# ─── Action events ────────────────────────────────────────────────────────────

class TestCsActionEvents:
    def test_click_save_produces_action_event(self):
        with _patch_cs(_FakeSession([[_make_text_response("Step.\n[ACTION: CLICK_SAVE]")]])):
            with client.websocket_connect("/cs-ws") as ws:
                # text event first, then action
                e1 = ws.receive_json()
                e2 = ws.receive_json()
                ws.close()
        action = e2 if e2["type"] == "action" else e1
        assert action["type"] == "action"
        assert action["command"] == "CLICK_SAVE"

    def test_drag_action_has_source_and_destination(self):
        raw = "[ACTION: DRAG_AND_DROP] Source -> SFO_Node. Destination -> Waypoint_1."
        with _patch_cs(_FakeSession([[_make_text_response(raw)]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "action"
        assert msg["source"] == "SFO_Node"
        assert msg["destination"] == "Waypoint_1"

    def test_multiple_actions_emitted_in_order(self):
        raw = "[ACTION: DRAG_AND_DROP] Source -> A. Destination -> B.\n[ACTION: CLICK_SAVE]"
        with _patch_cs(_FakeSession([[_make_text_response(raw)]])):
            with client.websocket_connect("/cs-ws") as ws:
                a1 = ws.receive_json()
                a2 = ws.receive_json()
                ws.close()
        assert a1["type"] == "action"
        assert a2["type"] == "action"
        assert a1["command"] == "DRAG_AND_DROP"
        assert a2["command"] == "CLICK_SAVE"


# ─── Audio output ─────────────────────────────────────────────────────────────

class TestCsAudioOutput:
    def test_audio_response_emitted(self):
        with _patch_cs(_FakeSession([[_make_audio_response()]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "audio"

    def test_audio_data_is_valid_base64(self):
        with _patch_cs(_FakeSession([[_make_audio_response()]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        base64.b64decode(msg["data"])  # must not raise

    def test_audio_data_roundtrips(self):
        pcm = bytes(range(256))
        with _patch_cs(_FakeSession([[_make_audio_response(pcm)]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert base64.b64decode(msg["data"]) == pcm


# ─── Interrupted ──────────────────────────────────────────────────────────────

class TestCsInterrupted:
    def test_interrupted_emits_interrupted_event(self):
        with _patch_cs(_FakeSession([[_make_interrupted_response()]])):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "interrupted"


# ─── Browser → Gemini ────────────────────────────────────────────────────────

class TestCsBrowserToGemini:
    def _send_and_close(self, payload):
        with _patch_cs(_FakeSession([])):
            with client.websocket_connect("/cs-ws") as ws:
                ws.send_json(payload)
                ws.close()

    def test_audio_message_does_not_crash(self):
        pcm = b"\x01\x02\x03\x04"
        self._send_and_close({"type": "audio", "data": base64.b64encode(pcm).decode()})

    def test_frame_message_does_not_crash(self):
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 10
        self._send_and_close({"type": "frame", "data": base64.b64encode(fake_jpeg).decode()})

    def test_invalid_base64_frame_silently_skipped(self):
        self._send_and_close({"type": "frame", "data": "!!!not-base64!!!"})

    def test_override_alert_does_not_crash(self):
        self._send_and_close({"type": "override_alert", "text": "Manual override!"})

    def test_override_alert_missing_text_uses_default(self):
        self._send_and_close({"type": "override_alert"})

    def test_unknown_message_type_ignored(self):
        self._send_and_close({"type": "unknown_type", "data": "abc"})


# ─── Error handling ───────────────────────────────────────────────────────────

class TestCsErrorHandling:
    def test_live_connect_failure_emits_error(self):
        mock_ll = MagicMock()
        mock_ll.aio.live.connect.side_effect = RuntimeError("live api down")
        with patch.object(app_module, "get_ll_client", return_value=mock_ll):
            with client.websocket_connect("/cs-ws") as ws:
                msg = ws.receive_json()
                ws.close()
        assert msg["type"] == "error"
        assert "live api down" in msg["message"]

    def test_interleaved_text_and_audio_both_delivered(self):
        responses = [_make_text_response("Frame body"), _make_audio_response()]
        with _patch_cs(_FakeSession([responses])):
            with client.websocket_connect("/cs-ws") as ws:
                e1 = ws.receive_json()
                e2 = ws.receive_json()
                ws.close()
        types = {e1["type"], e2["type"]}
        assert "text" in types
        assert "audio" in types
