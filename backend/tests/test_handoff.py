"""Tests for /handoff POST, GET /handoff/pending, and _normalize_ll_payload.

Phase 1 → Phase 2 handoff pipeline — no Gemini calls involved.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient

import main as app_module
from main import app, _normalize_ll_payload

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_handoff():
    app_module._pending_handoff = None
    app_module._handoff_seq = 0


SAMPLE_LL_PAYLOAD = {
    "severity": "red",
    "expected_latency_ms": 45,
    "delta_ms": 312,
    "delta_pct": 693.3,
    "diagnosis_category": "BGP_ROUTE_FLAP",
    "recommended_action": "Investigate BGP peer",
    "origin": "us-west-2",
    "destination": "eu-central-1",
    "affected_services": ["payment-gateway"],
    "timestamp": "2026-03-14T09:42:17Z",
}


# ── POST /handoff ─────────────────────────────────────────────────────────────

class TestHandoffPost:
    def setup_method(self):
        _reset_handoff()

    def test_valid_payload_returns_200(self):
        resp = client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        assert resp.status_code == 200

    def test_response_has_status_received(self):
        resp = client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        assert resp.json()["status"] == "received"

    def test_response_has_seq(self):
        resp = client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        assert "seq" in resp.json()

    def test_empty_payload_returns_400(self):
        resp = client.post("/handoff", json={})
        assert resp.status_code == 400

    def test_seq_increments_on_each_call(self):
        r1 = client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        r2 = client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        assert r2.json()["seq"] == r1.json()["seq"] + 1

    def test_stores_normalized_payload(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        assert app_module._pending_handoff is not None
        assert app_module._pending_handoff["severity"] == "CRITICAL"  # "red" → normalized


# ── GET /handoff/pending ──────────────────────────────────────────────────────

class TestHandoffPending:
    def setup_method(self):
        _reset_handoff()

    def test_204_when_no_handoff_stored(self):
        resp = client.get("/handoff/pending")
        assert resp.status_code == 204

    def test_200_after_post(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        resp = client.get("/handoff/pending")
        assert resp.status_code == 200

    def test_payload_key_present(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        body = client.get("/handoff/pending").json()
        assert "payload" in body

    def test_seq_key_present(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        body = client.get("/handoff/pending").json()
        assert "seq" in body

    def test_since_current_seq_returns_204(self):
        resp = client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        seq = resp.json()["seq"]
        poll = client.get(f"/handoff/pending?since={seq}")
        assert poll.status_code == 204

    def test_since_previous_seq_returns_200(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        poll = client.get("/handoff/pending?since=0")
        assert poll.status_code == 200

    def test_since_default_zero_returns_latest(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        body = client.get("/handoff/pending").json()
        assert body["payload"]["diagnosis_category"] == "BGP_ROUTE_FLAP"

    def test_payload_origin_normalized(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        body = client.get("/handoff/pending").json()
        assert body["payload"]["origin"] == "us-west-2"

    def test_last_post_wins(self):
        client.post("/handoff", json=SAMPLE_LL_PAYLOAD)
        client.post("/handoff", json={**SAMPLE_LL_PAYLOAD, "origin": "ap-northeast-1"})
        body = client.get("/handoff/pending").json()
        assert body["payload"]["origin"] == "ap-northeast-1"


# ── _normalize_ll_payload ─────────────────────────────────────────────────────

class TestNormalizePayload:
    def test_red_severity_maps_to_critical(self):
        assert _normalize_ll_payload({"severity": "red"})["severity"] == "CRITICAL"

    def test_amber_severity_maps_to_medium(self):
        assert _normalize_ll_payload({"severity": "amber"})["severity"] == "MEDIUM"

    def test_yellow_severity_maps_to_medium(self):
        assert _normalize_ll_payload({"severity": "yellow"})["severity"] == "MEDIUM"

    def test_green_severity_maps_to_low(self):
        assert _normalize_ll_payload({"severity": "green"})["severity"] == "LOW"

    def test_unknown_severity_uppercased(self):
        result = _normalize_ll_payload({"severity": "critical"})
        assert result["severity"] == "CRITICAL"

    def test_missing_severity_defaults_to_unknown(self):
        assert _normalize_ll_payload({})["severity"] == "UNKNOWN"

    def test_timestamp_passed_through_when_present(self):
        ts = "2026-01-01T00:00:00Z"
        result = _normalize_ll_payload({"timestamp": ts})
        assert result["timestamp"] == ts

    def test_missing_timestamp_injected(self):
        result = _normalize_ll_payload({})
        assert result["timestamp"]  # non-empty
        assert "T" in result["timestamp"]  # ISO format

    def test_all_required_keys_present(self):
        result = _normalize_ll_payload({})
        for key in ("severity", "expected_latency_ms", "delta_ms", "diagnosis_category",
                    "recommended_action", "origin", "destination", "affected_services",
                    "timestamp", "delta_pct"):
            assert key in result, f"missing key: {key}"

    def test_affected_services_passed_through(self):
        result = _normalize_ll_payload({"affected_services": ["svc-a", "svc-b"]})
        assert result["affected_services"] == ["svc-a", "svc-b"]

    def test_numeric_fields_passed_through(self):
        result = _normalize_ll_payload({"expected_latency_ms": 45, "delta_ms": 312})
        assert result["expected_latency_ms"] == 45
        assert result["delta_ms"] == 312

    def test_severity_case_insensitive(self):
        assert _normalize_ll_payload({"severity": "RED"})["severity"] == "CRITICAL"
        assert _normalize_ll_payload({"severity": "Red"})["severity"] == "CRITICAL"
