"""Tests for Gemini config builders, client factories, and system prompt content.

Validates that all three phase prompts contain required keywords and that
the Live API configs have the correct models, voices, and modalities.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from unittest.mock import patch, MagicMock
from google.genai import types

import main as app_module
from main import get_ll_config, get_cs_config, _live_client_for_key, _cs_live_client_for_key, _client_for_key
from prompt import SYSTEM_PROMPT, LL_SYSTEM_PROMPT, CS_SYSTEM_PROMPT, LL_MODEL, CS_MODEL


# ── Phase 2 SYSTEM_PROMPT ─────────────────────────────────────────────────────

class TestPhase2SystemPrompt:
    def test_contains_ge_open_tag(self):
        assert "GE_OPEN" in SYSTEM_PROMPT

    def test_contains_route_coords_tag(self):
        assert "ROUTE_COORDS" in SYSTEM_PROMPT

    def test_contains_all_four_frames(self):
        for frame in ("Frame 1", "Frame 2", "Frame 3", "Frame 4"):
            assert frame in SYSTEM_PROMPT, f"Missing {frame}"

    def test_contains_mermaid_instruction(self):
        assert "mermaid" in SYSTEM_PROMPT.lower()

    def test_contains_jira_ticket_instruction(self):
        assert "Jira" in SYSTEM_PROMPT or "jira" in SYSTEM_PROMPT.lower()

    def test_ge_open_tag_not_spoken(self):
        lower = SYSTEM_PROMPT.lower()
        assert ("silent" in lower or "never spoken" in lower
                or "not spoken" in lower or "do not reference" in lower)

    def test_midpoint_lat_documented(self):
        assert "midpoint_lat" in SYSTEM_PROMPT

    def test_audience_adaptation_mentioned(self):
        assert "CFO" in SYSTEM_PROMPT and "CTO" in SYSTEM_PROMPT


# ── Phase 1 LL_SYSTEM_PROMPT ─────────────────────────────────────────────────

class TestPhase1SystemPrompt:
    def test_contains_ge_open_instruction(self):
        assert "GE_OPEN" in LL_SYSTEM_PROMPT

    def test_contains_severity_levels(self):
        for level in ("Green", "Amber", "Red"):
            assert level in LL_SYSTEM_PROMPT, f"Missing severity: {level}"

    def test_contains_handoff_to_clarity_studio(self):
        lower = LL_SYSTEM_PROMPT.lower()
        assert "clarity studio" in lower

    def test_contains_audit_log_json(self):
        assert "severity" in LL_SYSTEM_PROMPT
        assert "diagnosis_category" in LL_SYSTEM_PROMPT

    def test_observe_first_rule_present(self):
        lower = LL_SYSTEM_PROMPT.lower()
        assert "observe" in lower or "describe" in lower

    def test_straight_line_test_defined(self):
        assert "STRAIGHT LINE" in LL_SYSTEM_PROMPT or "straight-line" in LL_SYSTEM_PROMPT.lower()

    def test_categories_defined(self):
        assert "Route intent mismatch" in LL_SYSTEM_PROMPT


# ── Phase 3 CS_SYSTEM_PROMPT ─────────────────────────────────────────────────

class TestPhase3SystemPrompt:
    def test_contains_valid_verdict(self):
        assert "ROUTE VALID" in CS_SYSTEM_PROMPT or "VALID" in CS_SYSTEM_PROMPT

    def test_contains_invalid_verdict(self):
        assert "ROUTE INVALID" in CS_SYSTEM_PROMPT or "INVALID" in CS_SYSTEM_PROMPT

    def test_contains_scan_complete(self):
        assert "SCAN COMPLETE" in CS_SYSTEM_PROMPT

    def test_contains_four_scan_steps(self):
        for step in ("STEP 1", "STEP 2", "STEP 3", "STEP 4"):
            assert step in CS_SYSTEM_PROMPT, f"Missing {step}"

    def test_no_action_tags_in_prompt(self):
        """Action tags removed — routing system handles correction automatically."""
        assert "ACTION: DRAG_AND_DROP" not in CS_SYSTEM_PROMPT
        assert "ACTION: CLICK_SAVE" not in CS_SYSTEM_PROMPT

    def test_prohibited_zone_defined(self):
        assert "PROHIBITED" in CS_SYSTEM_PROMPT or "Sierra Nevada" in CS_SYSTEM_PROMPT

    def test_approved_corridor_defined(self):
        assert "APPROVED CORRIDOR" in CS_SYSTEM_PROMPT or "I-10" in CS_SYSTEM_PROMPT

    def test_sfo_phx_circuit_present(self):
        assert "SFO" in CS_SYSTEM_PROMPT
        assert "PHX" in CS_SYSTEM_PROMPT

    def test_no_scripted_workflow(self):
        """Scripted NORMAL EXECUTION WORKFLOW was removed — agent must be purely reactive."""
        assert "NORMAL EXECUTION WORKFLOW" not in CS_SYSTEM_PROMPT

    def test_hard_rules_defined(self):
        assert "HARD RULES" in CS_SYSTEM_PROMPT or "Hard Rules" in CS_SYSTEM_PROMPT


# ── Model identifiers ─────────────────────────────────────────────────────────

class TestModelIdentifiers:
    def test_ll_model_is_native_audio(self):
        assert "native-audio" in LL_MODEL or "flash" in LL_MODEL

    def test_cs_model_is_flash(self):
        assert "flash" in CS_MODEL

    def test_ll_and_cs_models_are_strings(self):
        assert isinstance(LL_MODEL, str)
        assert isinstance(CS_MODEL, str)

    def test_ll_model_starts_with_models_prefix(self):
        assert LL_MODEL.startswith("models/")

    def test_cs_model_starts_with_models_prefix(self):
        assert CS_MODEL.startswith("models/")


# ── Live config builders ──────────────────────────────────────────────────────

class TestGetLLConfig:
    def setup_method(self):
        app_module._ll_config = None  # reset singleton

    def test_returns_live_connect_config(self):
        cfg = get_ll_config()
        assert isinstance(cfg, types.LiveConnectConfig)

    def test_response_modality_is_audio(self):
        cfg = get_ll_config()
        assert "AUDIO" in cfg.response_modalities

    def test_system_instruction_contains_ll_prompt(self):
        cfg = get_ll_config()
        parts_text = " ".join(p.text for p in cfg.system_instruction.parts if p.text)
        assert "Latency Lens" in parts_text

    def test_voice_is_zephyr(self):
        cfg = get_ll_config()
        voice_name = cfg.speech_config.voice_config.prebuilt_voice_config.voice_name
        assert voice_name == "Zephyr"

    def test_context_compression_configured(self):
        cfg = get_ll_config()
        assert cfg.context_window_compression is not None
        assert cfg.context_window_compression.trigger_tokens > 0

    def test_singleton_returns_same_object(self):
        app_module._ll_config = None
        c1 = get_ll_config()
        c2 = get_ll_config()
        assert c1 is c2


class TestGetCSConfig:
    def setup_method(self):
        app_module._cs_config = None  # reset singleton

    def test_returns_live_connect_config(self):
        cfg = get_cs_config()
        assert isinstance(cfg, types.LiveConnectConfig)

    def test_response_modality_is_audio(self):
        cfg = get_cs_config()
        assert "AUDIO" in cfg.response_modalities

    def test_system_instruction_contains_cs_prompt(self):
        cfg = get_cs_config()
        parts_text = " ".join(p.text for p in cfg.system_instruction.parts if p.text)
        assert "fiber route" in parts_text.lower() or "NOC" in parts_text

    def test_voice_is_aoede(self):
        cfg = get_cs_config()
        voice_name = cfg.speech_config.voice_config.prebuilt_voice_config.voice_name
        assert voice_name == "Aoede"

    def test_context_compression_configured(self):
        cfg = get_cs_config()
        assert cfg.context_window_compression is not None

    def test_singleton_returns_same_object(self):
        app_module._cs_config = None
        c1 = get_cs_config()
        c2 = get_cs_config()
        assert c1 is c2

    def test_ll_and_cs_configs_use_different_voices(self):
        ll = get_ll_config()
        cs = get_cs_config()
        ll_voice = ll.speech_config.voice_config.prebuilt_voice_config.voice_name
        cs_voice = cs.speech_config.voice_config.prebuilt_voice_config.voice_name
        assert ll_voice != cs_voice


# ── Client factory functions ──────────────────────────────────────────────────

class TestClientFactories:
    def test_live_client_uses_v1beta_when_key_provided(self):
        with patch("main.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            _live_client_for_key("fake-key")
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs.get("http_options", {}).get("api_version") == "v1beta"

    def test_cs_live_client_uses_v1alpha(self):
        with patch("main.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            _cs_live_client_for_key("fake-key")
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs.get("http_options", {}).get("api_version") == "v1alpha"

    def test_client_for_key_creates_new_client_when_key_given(self):
        with patch("main.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            _client_for_key("my-key")
            assert mock_cls.called
            assert mock_cls.call_args[1]["api_key"] == "my-key"

    def test_client_for_key_falls_back_to_singleton_when_no_key(self):
        mock_singleton = MagicMock()
        with patch.object(app_module, "get_gemini_client", return_value=mock_singleton):
            result = _client_for_key(None)
        assert result is mock_singleton

    def test_live_and_cs_clients_use_different_api_versions(self):
        """v1beta ≠ v1alpha — these must stay distinct."""
        calls = []
        with patch("main.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            _live_client_for_key("k")
            calls.append(mock_cls.call_args[1].get("http_options", {}).get("api_version"))
            _cs_live_client_for_key("k")
            calls.append(mock_cls.call_args[1].get("http_options", {}).get("api_version"))
        assert calls[0] != calls[1]
