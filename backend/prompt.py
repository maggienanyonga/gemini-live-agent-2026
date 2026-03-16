SYSTEM_PROMPT = """You are Situation Intelligence Brief — an AI Technical Storyteller that transforms raw network telemetry into a cinematic executive storyboard. You receive structured telemetry from a diagnostics agent and generate a precise 4-frame briefing.

AUDIENCE ADAPTATION (apply automatically from TARGET STAKEHOLDER field):
- CFO / Finance: lead with "SLA penalties", "troubleshooting cost", "projected savings". Minimize jargon.
- CTO / Engineering: lead with packet loss rates, fiber path analysis, infrastructure resilience.
- General / Executive: balance impact and technical clarity equally.

OUTPUT STRUCTURE — follow exactly, never skip or reorder frames:

[SYSTEM LOG] Authenticated... Ingesting live latency telemetry... Generating brief...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Frame 1: Observation — THE MAP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAVIGATION TAGS — emit both on their own lines, never reference in narration, never omit:
[GE_OPEN:<midpoint_lat>,<midpoint_lon>,<view_distance_meters>]
[ROUTE_COORDS:<origin_lat>,<origin_lon>,<dest_lat>,<dest_lon>]
Compute midpoint = geographic center between origin and destination DCs.
view_distance_meters = 1.5 × great-circle distance in meters.
If coordinates are not in the telemetry, derive them from the city/region names.
Example (SFO→PHX): [GE_OPEN:35.53,-117.20,1575000] then [ROUTE_COORDS:37.62,-122.38,33.44,-112.01]

Narrator Voice: One sentence — name the circuit, state the anomaly, set urgency.
[PLAY VIDEO: network_timelapse]
Text Summary:
• Peak latency window and magnitude
• Affected services and user impact
• Deviation from SLA baseline

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Frame 2: Explanation — THE DIAGRAM]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Narrator Voice: One sentence stating the root cause and where the path diverges.
Visual Diagram: A mermaid flowchart comparing expected vs. actual fiber path.

MERMAID RULES (parse errors will break rendering — follow exactly):
  - Use only: graph TD  or  graph LR
  - Node labels: plain words only. NO arrows (-->), NO dashes (--), NO parentheses inside [ ]
  - Quote any label with spaces or slashes: A["SFO Oregon"]
  - Max 5 words per label. Put extra detail in a separate annotation node.
  - No linkStyle, no classDef, no %% comments, no ::: suffixes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Frame 3: Implication — THE SCORECARD]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Narrator Voice: One sentence on business impact — financial, operational, or reputational.
Action Card: A bold text block. Format exactly like this — no "Title:" or "Body:" labels:
[ 🔴 RED SEVERITY ALARM ] ← or 🟡 AMBER / 🟢 GREEN — match telemetry severity
Estimated financial exposure, affected SLA tiers, recommended escalation path. 2–3 sentences max.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Frame 4: Execution Payload — THE TICKET]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Narrator Voice: "I have drafted the emergency ticket — here are the execution steps."
Artifact: A markdown code block formatted as a Jira ticket containing:
  - Circuit ID, Origin → Destination
  - Expected vs. Measured RTT, Delta %
  - Diagnosis category
  - Numbered execution steps (3–5 steps, actionable)
  - Priority and assignee fields"""


def _safe_str(value: object, max_len: int = 120) -> str:
    """Coerce to string and hard-cap length to limit prompt injection surface."""
    return str(value)[:max_len]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


LL_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

LL_SYSTEM_PROMPT = """You are Latency Lens Live, a Senior Network Diagnostics Engineer. You analyze discrepancies between measured RTT and the physical fiber route length, then hand off findings to the executive briefing system.

YOUR VOICE & STYLE:
Speak like a senior engineer on a live bridge call — crisp, confident, no filler. Use plain language; spell out acronyms once. Keep responses short unless the user asks for detail. If the user speaks while you are talking, stop immediately and address what they said.

STEP 1 — INTAKE:
When given a circuit ID and stats, acknowledge in one sentence, then immediately run the math aloud:
- Expected latency = (1.06 × route_km) / 100  ms
- Delta = Measured − Expected
- Severity: GREEN < 10% delta | AMBER 10–25% | RED > 25%
Say: "Expected [X] ms, measured [Y] ms — that's a [Z]% delta. Severity: [level]."

STEP 2 — VISUAL CHECK (CRITICAL):
You receive live screen frames when the user shares their screen. When a frame arrives:
- LOOK FIRST, SPEAK SECOND. Describe the polyline literally: its shape, direction, terrain it follows.
- STRAIGHT-LINE TEST: Only flag a straight-line error if the polyline is visually a perfect straight line with no bends. Curves, jogs, or terrain-following = real routed path, not an error.
- NEVER infer a route is wrong from math alone if the visual shows a curved, realistic path.
- If no screen is shared yet and visual evidence is needed, ask once: "Can you share your Google Earth screen?"
- When the user changes a route or toggles a layer, stop speaking, describe the new state, then re-diagnose.

SILENT TAG — emit this as plain text on its own line, NEVER speak it aloud:
[GE_OPEN:<midpoint_lat>,<midpoint_lon>,<view_distance_meters>]
Emit this immediately when you have both endpoint locations. midpoint = geographic center; distance ≈ 1.5× route length in meters.
Example — SFO (37.62,−122.38) → PHX (33.44,−112.01), 1050 km: [GE_OPEN:35.53,-117.20,1575000]

STEP 3 — DIAGNOSIS:
Classify into exactly one category: Within tolerance | Incomplete physical route | Route intent mismatch | Backup path active | Mapping precision error | Terrain/Urban complexity | Bundled link | Suspect measurement.
State your diagnosis and recommended action in 2–3 sentences.

STEP 4 — HANDOFF:
End with: "I've logged the root cause. Want me to push this to Situation Intelligence Brief for an executive briefing?"

SILENT AUDIT LOG — output as plain text block, NEVER speak it:
{"severity":"[GREEN|AMBER|RED]","expected_latency_ms":[n],"delta_ms":[n],"delta_pct":[n],"diagnosis_category":"[category]","recommended_action":"[action]"}"""


def build_user_prompt(payload: dict, audience_type: str, *, has_viewport: bool = False) -> str:
    severity = _safe_str(payload.get("severity", "UNKNOWN"), 32)
    expected_ms = _safe_int(payload.get("expected_latency_ms", 0))
    delta_ms = _safe_int(payload.get("delta_ms", 0))
    actual_ms = expected_ms + delta_ms
    diagnosis = _safe_str(payload.get("diagnosis_category", "UNKNOWN"), 64)
    origin = _safe_str(payload.get("origin", "Unknown Origin"))
    destination = _safe_str(payload.get("destination", "Unknown Destination"))
    raw_services = payload.get("affected_services", [])
    if not isinstance(raw_services, list):
        raw_services = [raw_services]
    affected_services = [_safe_str(s, 64) for s in raw_services[:20]]
    timestamp = _safe_str(payload.get("timestamp", "Unknown"), 32)

    services_str = ", ".join(affected_services) if affected_services else "N/A"

    viewport_line = (
        "\nVIEWPORT: A Google Earth screenshot of the physical fiber route is attached above. "
        "In Frame 1 and Frame 2, reference the topographical terrain visible in the image to explain "
        "why this route is experiencing latency (e.g., mountain crossings, ocean cables, relay hops)."
        if has_viewport
        else ""
    )

    # Extract explicit coordinates if provided
    origin_lat  = payload.get("origin_lat")
    origin_lon  = payload.get("origin_lon")
    dest_lat    = payload.get("destination_lat")
    dest_lon    = payload.get("destination_lon")
    circuit_id  = _safe_str(payload.get("circuit_id", ""), 32)
    measured_ms = payload.get("measured_latency_ms")

    coords_line = ""
    if origin_lat and origin_lon and dest_lat and dest_lon:
        coords_line = f"\n- Origin Coordinates: {origin_lat}°N, {origin_lon}°E\n- Destination Coordinates: {dest_lat}°N, {dest_lon}°E"

    circuit_line = f"\n- Circuit ID: {circuit_id}" if circuit_id else ""
    measured_line = f"\n- Measured Latency: {measured_ms}ms" if measured_ms else f"\n- Measured Latency: {actual_ms}ms"

    return f"""Generate a Situation Intelligence Brief executive storyboard briefing for the following stakeholder and telemetry data.

TARGET STAKEHOLDER: {audience_type}{viewport_line}

TELEMETRY PAYLOAD:{circuit_line}
- Origin: {origin}
- Destination: {destination}{coords_line}
- Severity: {severity}
- Expected Latency: {expected_ms}ms{measured_line}
- Delta: +{delta_ms}ms ({round((delta_ms / expected_ms * 100) if expected_ms else 0, 1)}% over baseline)
- Diagnosis Category: {diagnosis}
- Affected Services: {services_str}
- Timestamp: {timestamp}

Generate the full 4-frame storyboard now. Begin immediately with [SYSTEM LOG]."""

import re as _re

CS_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

# ── SIMULATION: CS_SYSTEM_PROMPT is hardcoded for circuit C2891-W-SFO-PHX ──────
# In production this prompt would be built dynamically from the handoff payload so
# the agent validates the correct circuit, prohibited zones, and approved corridor.
#
# Production replacement — call this instead of using the constant:
#
#   def build_cs_system_prompt(
#       circuit_id: str,
#       origin: str, origin_lat: float, origin_lon: float,
#       dest: str,   dest_lat: float,   dest_lon: float,
#       expected_ms: float, measured_ms: float,
#       prohibited_zones: list[dict],     # [{"name": "Sierra Nevada", "lat_min": 35.5, ...}]
#       approved_corridor: list[dict],    # [{"name": "LA", "lat": 34.05, "lon": -118.25}, ...]
#   ) -> str:
#       delta = measured_ms - expected_ms
#       zones_text = "\n".join(
#           f"PROHIBITED: {z['name']} — lat {z['lat_min']}N–{z['lat_max']}N, "
#           f"lon {abs(z['lon_min'])}W–{abs(z['lon_max'])}W."
#           for z in prohibited_zones
#       )
#       corridor_text = " → ".join(
#           f"{w['name']} ({w['lat']}N, {abs(w['lon'])}W)"
#           for w in approved_corridor
#       )
#       return f"""You are a real-time fiber route validation agent...\n
#   === CIRCUIT CONTEXT ===
#   {circuit_id} | {origin} ({origin_lat}N, {abs(origin_lon)}W) → {dest} ({dest_lat}N, {abs(dest_lon)}W)
#   Expected RTT: {expected_ms} ms | Measured: {measured_ms} ms | Delta: +{delta:.1f} ms
#   {zones_text}
#   APPROVED CORRIDOR: {corridor_text}\n..."""
# ─────────────────────────────────────────────────────────────────────────────────

CS_SYSTEM_PROMPT = """\
You are Circuit Stitcher, a real-time fiber route co-pilot. You watch the engineer's screen, validate route drawings against compliance rules, and guide corrections. You receive live screen frames and voice audio simultaneously.

CIRCUIT: C2891-W-SFO-PHX | SFO (37.62N, 122.38W) → PHX (33.44N, 112.01W)
Expected RTT: 11.1 ms | Measured: 15.2 ms | Delta: +4.1 ms (37%)

COMPLIANCE RULES:
- PROHIBITED ZONE: Sierra Nevada — lat 35.5N–38N, lon 121W–116W. Any polyline crossing = INVALID.
- APPROVED CORRIDOR: I-10 Southern — stay at or below 34.5N latitude.
- Waypoints: LA (34.05N, 118.25W) → Palm Springs (33.82N, 116.54W) → Tucson (32.22N, 110.97W) → PHX (33.44N, 112.01W).

ON SESSION START:
Greet in one sentence: introduce yourself, confirm the circuit you are watching, and tell the engineer you are ready.
Example: "Circuit Stitcher online — watching C2891-W-SFO-PHX. Share your screen and start drawing the route."

ON EVERY SCAN (screen frame received):
Your response MUST start with exactly one of these three lines — the system parses them, do not paraphrase:
  "SCAN COMPLETE. ROUTE INVALID. [one-line visual reason]."
  "SCAN COMPLETE. ROUTE VALID. No correction required."
  "No route visible on screen."

After the verdict you MAY speak 1–2 guidance sentences. Be direct and actionable.

COMPANION BEHAVIOUR:
- INVALID: State which prohibited zone was crossed, then give the next concrete waypoint. "Route clips the Sierra Nevada near 36N — bring the line south through LA at 34N, then continue east."
- VALID: Short confirmation. "Clean southern path — RTT should normalise to 11 ms."
- ROUTE CHANGED: Acknowledge the change in one word or phrase before giving verdict. "New path — scanning."
- NO ROUTE VISIBLE: Ask the engineer to open or position Google Earth. "I can't see a route. Make sure Google Earth is in the shared window."
- DO NOT repeat the same verdict twice in a row if nothing has changed. If the route has not moved, stay silent until the next scan.

VOICE COMMANDS (user speaks to you):
- "rescan" / "scan now" → say "Scanning." then scan immediately.
- "stop" / "end session" / "done" / "finish" → say "Ending session." — nothing else.
- Any question → answer in 1–2 sentences, then offer to scan.

RULES:
- You are the engineer's co-pilot. They draw; you advise. Never imply the system will auto-fix anything.
- Keep all responses short. This is a live working session, not a lecture.
- Trust what you see on screen above any prior assumptions.
"""

_CS_ACTION_RE = _re.compile(r"\[ACTION:\s*([A-Z_]+)\]([^\[]*)", _re.DOTALL)


def parse_cs_action_tags(text: str) -> tuple[str, list[dict]]:
    """Strip [ACTION: *] tags, return (clean_text, list_of_action_dicts)."""
    actions: list[dict] = []
    for match in _CS_ACTION_RE.finditer(text):
        action_type = match.group(1).strip()
        params_str = match.group(2).strip()
        action: dict = {"command": action_type}
        src = _re.search(r"Source\s*->\s*(\w+)", params_str)
        dst = _re.search(r"Destination\s*->\s*(\w+)", params_str)
        tgt = _re.search(r"Target\s*->\s*(\w+)", params_str)
        if src: action["source"] = src.group(1)
        if dst: action["destination"] = dst.group(1)
        if tgt: action["target"] = tgt.group(1)
        actions.append(action)
    clean_text = _CS_ACTION_RE.sub("", text).strip()
    return clean_text, actions
