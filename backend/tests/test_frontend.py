"""Frontend static-file smoke tests — run without a browser.

Catches syntax errors, missing functions, broken HTML structure, and stale
third-party API references before the app is opened in a browser.
"""
import re
import subprocess
import sys
import os

FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)
APP_JS   = os.path.join(FRONTEND_DIR, "app.js")
INDEX_HTML = os.path.join(FRONTEND_DIR, "index.html")
STYLES_CSS = os.path.join(FRONTEND_DIR, "styles.css")


def _js() -> str:
    with open(APP_JS) as f:
        return f.read()


def _html() -> str:
    with open(INDEX_HTML) as f:
        return f.read()


def _css() -> str:
    with open(STYLES_CSS) as f:
        return f.read()


# ── File existence ────────────────────────────────────────────────────────────

class TestFilesExist:
    def test_app_js_exists(self):
        assert os.path.isfile(APP_JS)

    def test_index_html_exists(self):
        assert os.path.isfile(INDEX_HTML)

    def test_styles_css_exists(self):
        assert os.path.isfile(STYLES_CSS)


# ── JS syntax ─────────────────────────────────────────────────────────────────

class TestJsSyntax:
    def test_app_js_has_no_syntax_errors(self):
        result = subprocess.run(
            ["node", "--check", APP_JS],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"


# ── No stale API references ───────────────────────────────────────────────────

class TestNoStaleApiReferences:
    def test_no_google_maps_js_api_in_js(self):
        """google.maps.Map requires billing — must not appear in app.js."""
        assert "new google.maps.Map" not in _js()

    def test_no_google_maps_marker_in_js(self):
        assert "google.maps.Marker" not in _js()
        assert "AdvancedMarkerElement" not in _js()

    def test_no_google_maps_api_script_in_html(self):
        """The Maps JS API loader must not be in index.html (it requires billing)."""
        assert "maps.googleapis.com/maps/api/js" not in _html()

    def test_no_leaflet_in_html(self):
        """Leaflet removed — only Google products used for maps."""
        assert "leaflet" not in _html().lower()

    def test_google_static_maps_used_in_js(self):
        assert "maps.googleapis.com/maps/api/staticmap" in _js()


# ── Required JS functions (all three phases) ─────────────────────────────────

class TestRequiredFunctions:
    # Phase 1 — Latency Lens
    def test_switch_phase_defined(self):
        assert "function switchPhase" in _js()

    def test_open_google_earth_defined(self):
        assert "function openGoogleEarth" in _js()

    def test_get_api_key_defined(self):
        assert "function getApiKey" in _js()

    # Phase 2 — Situation Intelligence Brief
    def test_cs_render_video_player_defined(self):
        assert "function csRenderVideoPlayer" in _js()

    def test_build_user_prompt_equivalent_in_cs(self):
        assert "csRenderMermaid" in _js()

    # Phase 3 — Situation Intelligence Brief
    def test_cs3_start_session_defined(self):
        assert "function cs3StartSession" in _js()

    def test_cs3_stop_session_defined(self):
        assert "function cs3StopSession" in _js()

    def test_cs3_render_route_map_defined(self):
        assert "function cs3RenderRouteMap" in _js()

    def test_cs3_animate_i10_route_defined(self):
        assert "function cs3AnimateI10Route" in _js()

    def test_cs3_stop_screen_share_defined(self):
        assert "function cs3StopScreenShare" in _js()

    def test_cs3_check_valid_verdict_defined(self):
        assert "function cs3CheckValidVerdict" in _js()

    def test_cs3_check_reroute_phrase_defined(self):
        assert "function cs3CheckReroutePhrase" in _js()

    def test_cs3_show_approval_bar_defined(self):
        assert "function cs3ShowApprovalBar" in _js()

    def test_cs3_approve_route_defined(self):
        assert "function cs3ApproveRoute" in _js()

    def test_cs3_update_route_status_defined(self):
        assert "function cs3UpdateRouteStatus" in _js()

    def test_static_map_helper_in_js(self):
        assert "function _staticMap" in _js()

    def test_ensure_google_maps_not_defined(self):
        """ensureGoogleMaps was removed when we switched to free Embed API."""
        assert "function ensureGoogleMaps" not in _js()


# ── Required state variables ──────────────────────────────────────────────────

class TestRequiredStateVariables:
    def test_cs3_route_was_invalid_flag(self):
        assert "_cs3RouteWasInvalid" in _js()

    def test_cs3_anim_triggered_flag(self):
        assert "_cs3AnimTriggered" in _js()

    def test_ge_window_ref_defined(self):
        assert "geWindowRef" in _js()

    def test_cs3_pending_handoff_defined(self):
        assert "cs3PendingHandoff" in _js()

    def test_i10_nodes_defined(self):
        assert "_I10_NODES" in _js()


# ── HTML structure ────────────────────────────────────────────────────────────

class TestHtmlStructure:
    def test_three_phase_tabs_present(self):
        html = _html()
        assert 'data-phase="1"' in html
        assert 'data-phase="2"' in html
        assert 'data-phase="3"' in html

    def test_api_key_input_present(self):
        assert 'id="apiKeyInput"' in _html()

    def test_phase3_route_map_container(self):
        assert 'id="cs3-route-map"' in _html()

    def test_phase3_transcript_present(self):
        assert 'id="cs3-transcript"' in _html()

    def test_phase3_session_button_present(self):
        assert 'id="cs3-session-btn"' in _html()

    def test_phase3_screen_button_present(self):
        assert 'id="cs3-screen-btn"' in _html()

    def test_phase3_route_status_badge(self):
        assert 'id="cs3-route-status"' in _html()

    def test_phase3_mic_badge_present(self):
        assert 'id="cs3-mic-badge"' in _html()

    def test_phase3_screen_badge_present(self):
        assert 'id="cs3-screen-badge"' in _html()

    def test_mermaid_script_loaded(self):
        assert "mermaid" in _html()

    def test_title_is_enterprise_suite(self):
        assert "Enterprise Suite" in _html()

    def test_no_inline_google_maps_script_tag(self):
        assert "maps.googleapis.com/maps/api/js" not in _html()


# ── Google Static Maps usage (Phase 2 + 3) ───────────────────────────────────

class TestGoogleStaticMapUsage:
    def test_static_map_helper_defined(self):
        assert "function _staticMap" in _js()

    def test_static_map_uses_hybrid_type(self):
        assert "maptype=hybrid" in _js()

    def test_bad_route_drawn_in_red(self):
        assert "ef4444" in _js()

    def test_i10_route_drawn_in_green(self):
        assert "22c55e" in _js()

    def test_no_leaflet_calls_in_js(self):
        assert "L.map(" not in _js()
        assert "L.tileLayer(" not in _js()
        assert "L.polyline(" not in _js()

    def test_no_embed_iframe_in_route_map(self):
        """Embed API requires GCP — must not be used."""
        assert "maps/embed/v1" not in _js()

    def test_no_esri_tiles(self):
        assert "arcgisonline.com" not in _js()


# ── Phase 3 verdict detection wiring ─────────────────────────────────────────

class TestVerdictDetection:
    def test_valid_regex_in_check_verdict(self):
        js = _js()
        # cs3CheckValidVerdict must test for VALID
        fn_start = js.find("function cs3CheckValidVerdict")
        fn_end = js.find("\nfunction", fn_start + 1)
        fn_body = js[fn_start:fn_end]
        assert "VALID" in fn_body

    def test_invalid_regex_in_check_verdict(self):
        js = _js()
        fn_start = js.find("function cs3CheckValidVerdict")
        fn_end = js.find("\nfunction", fn_start + 1)
        fn_body = js[fn_start:fn_end]
        assert "INVALID" in fn_body

    def test_ge_window_closed_on_invalid(self):
        js = _js()
        fn_start = js.find("function cs3CheckValidVerdict")
        fn_end = js.find("\nfunction", fn_start + 1)
        fn_body = js[fn_start:fn_end]
        assert "geWindowRef" in fn_body
        assert ".close()" in fn_body

    def test_check_valid_verdict_called_in_message_handler(self):
        assert "cs3CheckValidVerdict(msg.content)" in _js()


# ── CSS health ────────────────────────────────────────────────────────────────

class TestCssHealth:
    def test_cs3_route_status_badge_defined(self):
        assert "cs3-route-status-badge" in _css()

    def test_cs3_approval_bar_defined(self):
        assert "cs3-approval-bar" in _css()

    def test_cs3_map_fill_defined(self):
        assert "cs3-map-fill" in _css()

    def test_route_map_absolute_positioning(self):
        css = _css()
        # #cs3-route-map must be position:absolute for the map to fill its container
        idx = css.find("#cs3-route-map")
        snippet = css[idx:idx + 200]
        assert "absolute" in snippet
