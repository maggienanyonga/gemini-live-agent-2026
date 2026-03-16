// ══════════════════════════════════════════════════════════════════════════════
// Clarity Studio — Frontend
// ══════════════════════════════════════════════════════════════════════════════
//
// API SIMULATIONS & KEY REQUIREMENTS
// -----------------------------------
//  Feature                     Status           Requires / Notes
//  ──────────────────────────────────────────────────────────────────────────
//  Gemini Live (Phase 1 & 3)   ✅ LIVE          API key in header input
//  Gemini SSE briefing (Ph. 2) ✅ LIVE          API key in header input
//  Google Maps Static API      🔶 KEY REQUIRED  Maps Platform key → _staticMap()
//                                               Returns null silently if absent
//                                               I-10 route overlay disabled
//  Google Earth Web Embed      🔶 SIMULATED     Maps Platform billing + waitlist
//                                               → wrong_path.png placeholder
//                                               Production iframe commented in
//                                               cs3RenderRouteMap() + index.html
//  Nano Banana image gen       🔶 KEY REQUIRED  GEMINI_API_KEY (paid tier)
//                                               Falls back to wrong_path.png
//                                               6-model chain in backend
//  I-10 route waypoints        🔶 HARDCODED     C2891-W-SFO-PHX only
//                                               See _I10_NODES — production fetch
//                                               commented above the constant
//  Circuit Stitcher context    🔶 HARDCODED     CS_SYSTEM_PROMPT in prompt.py
//                                               See build_cs_system_prompt comment
//  Vertex AI RAG               🔶 SIMULATED     GCP + Vertex AI billing
//                                               SLA doc injected as context;
//                                               production code commented in
//                                               backend/main.py stream_gemini()
// ══════════════════════════════════════════════════════════════════════════════

// ─── Theme ────────────────────────────────────────────────────────────────────
const _MERMAID_DARK = {
  theme: 'dark',
  themeVariables: {
    background: '#111520', primaryColor: '#1e3a5f',
    primaryTextColor: '#e2e8f0', primaryBorderColor: '#2563eb',
    lineColor: '#3b82f6', secondaryColor: '#181d2a',
    tertiaryColor: '#0a0c10', edgeLabelBackground: '#111520',
    nodeBorder: '#2563eb', clusterBkg: '#181d2a',
  },
};
const _MERMAID_LIGHT = {
  theme: 'default',
  themeVariables: {
    background: '#ffffff', primaryColor: '#dbeafe',
    primaryTextColor: '#0f172a', primaryBorderColor: '#2563eb',
    lineColor: '#2563eb', secondaryColor: '#f1f5f9',
    tertiaryColor: '#f8fafc', edgeLabelBackground: '#ffffff',
    nodeBorder: '#2563eb', clusterBkg: '#f1f5f9',
  },
};

function _currentTheme() {
  return document.documentElement.getAttribute('data-theme') || 'light';
}

function _applyMermaidTheme(theme) {
  const vars = theme === 'dark' ? _MERMAID_DARK : _MERMAID_LIGHT;
  mermaid.initialize({ startOnLoad: false, flowchart: { curve: 'basis' }, ...vars });
}

function toggleTheme() {
  const next = _currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  document.getElementById('themeToggle').textContent = next === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('cs-theme', next);
  _applyMermaidTheme(next);
}

// Restore saved theme on load (default: light)
(function() {
  const saved = localStorage.getItem('cs-theme') || 'light';
  if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = saved === 'dark' ? '☀️' : '🌙';
    // Restore saved API key
    const savedKey = localStorage.getItem('cs-api-key') || '';
    const inp = document.getElementById('apiKeyInput');
    if (inp && savedKey) inp.value = savedKey;
    // Restore last LL audit log (keeps data alive for re-pushing to CS)
    try {
      const savedLog = localStorage.getItem('ll-last-audit-log');
      if (savedLog) llLastAuditLog = JSON.parse(savedLog);
    } catch (e) {}

    // Restore last CS handoff — show banner in Phase 2
    try {
      const savedHandoff = localStorage.getItem('cs-last-handoff');
      if (savedHandoff) {
        llPendingHandoff = JSON.parse(savedHandoff);
        if (llPendingHandoff) csShowHandoffBanner(llPendingHandoff);
      }
    } catch (e) {}

    // Restore last CS3 handoff — show banner and map in Phase 3
    try {
      const savedCS3 = localStorage.getItem('cs3-last-handoff');
      if (savedCS3) {
        cs3PendingHandoff = JSON.parse(savedCS3);
        if (cs3PendingHandoff) {
          cs3ShowHandoffBanner(cs3PendingHandoff);
          cs3PopulateTicket(cs3PendingHandoff);
          // Map rendered on switchPhase(3), or immediately if already on Phase 3
          if (activePhase === 3) cs3RenderRouteMap(cs3PendingHandoff);
        }
      }
    } catch (e) {}

    // Route to tab from URL hash (e.g. #clarity-studio)
    const phase = _phaseFromHash();
    if (phase) switchPhase(phase);
  });
  _applyMermaidTheme(saved);
})();

// ─── Quake Console ────────────────────────────────────────────────────────────
let _quakeOpen = false;
let _quakeCount = 0;

function toggleQuakeConsole() {
  _quakeOpen = !_quakeOpen;
  const el = document.getElementById('quake-console');
  const btn = document.getElementById('logsToggle');
  if (el) {
    el.style.display = _quakeOpen ? 'flex' : 'none';
    el.classList.toggle('open', _quakeOpen);
  }
  if (btn) btn.classList.toggle('active', _quakeOpen);
}

function quakeClear() {
  const log = document.getElementById('quake-log');
  if (log) log.innerHTML = '';
  _quakeCount = 0;
  _updateQuakeCount();
}

function _updateQuakeCount() {
  const el = document.getElementById('quake-count');
  if (el) el.textContent = `${_quakeCount} entr${_quakeCount === 1 ? 'y' : 'ies'}`;
}

// source: 'p1'|'p2'|'p3'|'sys'  type: 'info'|'warn'|'error'|'system'
function _dbgLog(source, msg, type = 'info') {
  console.log(`[${source.toUpperCase()}]`, msg);
  const log = document.getElementById('quake-log');
  if (!log) return;
  const now = new Date();
  const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}.${String(now.getMilliseconds()).padStart(3,'0')}`;
  const row = document.createElement('div');
  row.className = `quake-entry type-${type}`;
  row.innerHTML = `<span class="quake-ts">${ts}</span><span class="quake-src ${source}">${source.toUpperCase()}</span><span class="quake-msg">${String(msg).replace(/</g,'&lt;')}</span>`;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
  _quakeCount++;
  _updateQuakeCount();
}

// ─── API Key ──────────────────────────────────────────────────────────────────
function getApiKey() {
  return document.getElementById('apiKeyInput')?.value.trim() || '';
}
function saveApiKey(val) {
  if (val) localStorage.setItem('cs-api-key', val);
  else localStorage.removeItem('cs-api-key');
}

// ─── Google Maps Static API helper ────────────────────────────────────────────
// REQUIRES: Google Maps Platform API key with "Maps Static API" enabled.
// Without a key this returns null and all route overlay images are skipped.
//
// To enable in production:
//   1. Go to console.cloud.google.com → APIs & Services → Credentials
//   2. Create an API key, restrict to "Maps Static API"
//   3. Enable billing on the GCP project (Static Maps: $2 per 1,000 requests)
//   4. Paste the key into the API Key field in the app header
//
// When the key is present, this builds URLs like:
//   https://maps.googleapis.com/maps/api/staticmap?size=640x400&maptype=hybrid
//     &path=color:0x22c55ecc|weight:4|37.62,-122.38|34.05,-118.25|...
//     &key=AIza...
function _staticMap(pathStr, markersArr, size = '640x400') {
  const key = getApiKey();
  if (!key) return null;   // silently disabled — no key provided
  let url = `https://maps.googleapis.com/maps/api/staticmap?size=${size}&maptype=hybrid`;
  if (pathStr) url += `&path=${pathStr}`;
  for (const m of markersArr) url += `&markers=${m}`;
  url += `&key=${encodeURIComponent(key)}`;
  return url;
}

function toggleApiKeyVisibility() {
  const inp = document.getElementById('apiKeyInput');
  if (!inp) return;
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

// ─── Mermaid Init ─────────────────────────────────────────────────────────────
mermaid.initialize({ startOnLoad: false, flowchart: { curve: 'basis' }, ..._MERMAID_LIGHT });

// ─── Phase Switcher ───────────────────────────────────────────────────────────
let activePhase = 1;

// Saved status for each phase so switching back restores the right label
let _llStatus  = { cls: '',       label: 'Disconnected' };
let _csStatus  = { cls: '',       label: 'Standby' };

function _applyStatus(cls, label) {
  document.getElementById('statusDot').className = 'status-dot ' + (cls || '');
  document.getElementById('statusLabel').textContent = label;
}

function switchPhase(phase) {
  _dbgLog('sys', `Switch → Phase ${phase}`, 'system');
  activePhase = phase;
  document.querySelectorAll('.phase-view').forEach(el => el.classList.remove('active'));
  document.getElementById(`phase-${phase}`).classList.add('active');
  document.querySelectorAll('.phase-tab[data-phase]').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.phase) === phase);
  });
  if (phase === 1)      _applyStatus(_llStatus.cls,  _llStatus.label);
  else if (phase === 2) _applyStatus(_csStatus.cls,  _csStatus.label);
  else                  _applyStatus(_cs3Status.cls, _cs3Status.label);
  // Re-render CS3 map when switching into Phase 3
  if (phase === 3) {
    setTimeout(() => cs3RenderRouteMap(cs3PendingHandoff || {}), 80);
  }
  // Update URL hash without adding a history entry
  const slug = phase === 1 ? 'latency-lens' : phase === 2 ? 'clarity-studio' : 'circuit-stitcher';
  history.replaceState(null, '', '#' + slug);
}

function _phaseFromHash() {
  const h = location.hash.replace('#', '');
  if (h === 'latency-lens')    return 1;
  if (h === 'clarity-studio')  return 2;
  if (h === 'circuit-stitcher') return 3;
  // also accept bare numbers: #1 #2 #3
  const n = parseInt(h);
  if (n >= 1 && n <= 3) return n;
  return null;
}

window.addEventListener('hashchange', () => {
  const phase = _phaseFromHash();
  if (phase && phase !== activePhase) switchPhase(phase);
});

// ─── Google Earth Auto-Navigation ─────────────────────────────────────────────
let geWindowRef = null;

function openGoogleEarth(lat, lon, dist) {
  const url = `https://earth.google.com/web/@${lat},${lon},0a,${dist}d,35y,0h,0t,0r`;
  const halfW = Math.floor(screen.availWidth / 2);
  geWindowRef = window.open(
    url, 'google-earth',
    `popup,left=${halfW},top=0,width=${halfW},height=${screen.availHeight}`
  );
  try { window.moveTo(0, 0); window.resizeTo(halfW, screen.availHeight); } catch (e) {}

  // In Phase 1, also add a GE nav card to the transcript
  if (activePhase === 1) {
    const container = document.getElementById('ll-transcript');
    if (container) {
      const div = document.createElement('div');
      div.className = 'll-transcript-entry ll-entry-system';
      div.innerHTML =
        `<span class="ll-transcript-time">${llTimestamp()}</span>` +
        `<span class="ll-ge-nav">` +
        `<span class="ll-ge-label">🌍 Google Earth</span>` +
        `<a class="ll-ge-link" href="${url}" target="_blank" rel="noopener">Open route view</a>` +
        `</span>`;
      container.appendChild(div);
      container.scrollTop = container.scrollHeight;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  PHASE 1 — LATENCY LENS
// ═══════════════════════════════════════════════════════════════════════════════

// ─── LL State ─────────────────────────────────────────────────────────────────
let llWs = null;
let llCaptureCtx = null;
let llWorkletNode = null;
let llMicStream = null;
let llScreenStream = null;
let llScreenInterval = null;
let llScreenVideo = null;
let llSessionActive = false;
let llScreenActive = false;
let llAISpeaking = false;

let llPlaybackCtx = null;
let llNextPlayTime = 0;
const llActiveSources = [];

let llTextAccum = '';
let llLastAuditLog = null;
let llPendingHandoff = null;   // set by pushToClarity, consumed by csApplyHandoff
let llAutoPushTriggered = false;   // prevents double-firing within one session
let _csPendingAutoGenerate = false; // deferred CS generation while LL session is live

// ─── LL Audio Playback ────────────────────────────────────────────────────────
function llEnsurePlaybackCtx() {
  if (!llPlaybackCtx) {
    llPlaybackCtx = new AudioContext({ sampleRate: 24000 });
    llNextPlayTime = 0;
  }
  if (llPlaybackCtx.state === 'suspended') llPlaybackCtx.resume();
}

function llScheduleAudio(base64Data) {
  llEnsurePlaybackCtx();
  const binary = atob(base64Data);
  const int16 = new Int16Array(binary.length / 2);
  for (let i = 0; i < int16.length; i++) {
    int16[i] = binary.charCodeAt(i * 2) | (binary.charCodeAt(i * 2 + 1) << 8);
  }
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / (int16[i] < 0 ? 32768 : 32767);
  }
  const buf = llPlaybackCtx.createBuffer(1, float32.length, 24000);
  buf.copyToChannel(float32, 0);
  const src = llPlaybackCtx.createBufferSource();
  src.buffer = buf;
  src.connect(llPlaybackCtx.destination);
  llActiveSources.push(src);
  src.onended = () => {
    const idx = llActiveSources.indexOf(src);
    if (idx !== -1) llActiveSources.splice(idx, 1);
    if (llActiveSources.length === 0) llSetAISpeaking(false);
  };
  const startAt = Math.max(llPlaybackCtx.currentTime + 0.04, llNextPlayTime);
  src.start(startAt);
  llNextPlayTime = startAt + buf.duration;
  llSetAISpeaking(true);
}

function llClearAudioQueue() {
  for (const src of [...llActiveSources]) {
    try { src.stop(); } catch (e) {}
  }
  llActiveSources.length = 0;
  llNextPlayTime = llPlaybackCtx ? llPlaybackCtx.currentTime : 0;
  llSetAISpeaking(false);
}

// ─── LL Utility ───────────────────────────────────────────────────────────────
function llArrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.byteLength; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function llTimestamp() {
  return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function llEscapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// ─── LL Transcript ────────────────────────────────────────────────────────────
function llAppendTranscript(text, type = 'ai') {
  if (!text || !text.trim()) return;
  _dbgLog('p1', text, type === 'error' ? 'error' : type === 'system' ? 'system' : 'info');
  const container = document.getElementById('ll-transcript');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `ll-transcript-entry ll-entry-${type}`;
  div.innerHTML = `<span class="ll-transcript-time">${llTimestamp()}</span>${llEscapeHtml(text)}`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function llClearTranscript() {
  document.getElementById('ll-transcript').innerHTML = '';
  llTextAccum = '';
  llAutoPushTriggered = false;
  _csPendingAutoGenerate = false;
}

// ─── LL Text / Audit Log Handling ─────────────────────────────────────────────
function llHandleText(chunk) {
  llTextAccum += chunk;
  // Strip and fire [GE_OPEN:...] silent commands
  llTextAccum = llTextAccum.replace(
    /\[GE_OPEN:([-\d.]+),([-\d.]+),([\d.]+)\]/g,
    (_, lat, lon, dist) => { openGoogleEarth(parseFloat(lat), parseFloat(lon), parseFloat(dist)); return ''; }
  );
  if (llTextAccum.length > 50_000) {
    llAppendTranscript('[Text buffer overflow — cleared]', 'error');
    llTextAccum = '';
    return;
  }
  const braceOpen = llTextAccum.indexOf('{');
  if (braceOpen !== -1) {
    const braceClose = llTextAccum.lastIndexOf('}');
    if (braceClose > braceOpen) {
      const candidate = llTextAccum.slice(braceOpen, braceClose + 1);
      try {
        const parsed = JSON.parse(candidate);
        if (parsed.severity && parsed.diagnosis_category) {
          llRenderAuditLog(parsed);
          const before = llTextAccum.slice(0, braceOpen).trim();
          const after  = llTextAccum.slice(braceClose + 1).trim();
          llCheckAutoPush(before + ' ' + after);
          if (before) llAppendTranscript(before, 'ai');
          if (after)  llAppendTranscript(after, 'ai');
          llTextAccum = '';
          return;
        }
      } catch (e) { /* incomplete JSON */ }
    }
    return; // hold while building toward JSON
  }
  llCheckAutoPush(llTextAccum);
  llAppendTranscript(llTextAccum, 'ai');
  llTextAccum = '';
}

// ─── LL Auto-Push Detection ────────────────────────────────────────────────────
function llCheckAutoPush(text) {
  if (!llLastAuditLog || llAutoPushTriggered) return;
  const t = text.toLowerCase();
  // Skip the question form ("would you like me to push", "shall I push")
  if (/would you like|shall i|should i/.test(t)) return;
  // Match affirmative push action directed at Clarity Studio
  const isPushAction = /i(?:'m| am| will|'ll)(?: now)? push|pushing (?:this|the|now)|pushed (?:this|the)|sending (?:this|the) to clarity/.test(t);
  if (isPushAction && t.includes('clarity')) {
    llAutoPushTriggered = true;
    setTimeout(pushToClarity, 600);
  }
}

// ─── LL Audit Log ─────────────────────────────────────────────────────────────
function llRenderAuditLog(log) {
  llLastAuditLog = log;
  try { localStorage.setItem('ll-last-audit-log', JSON.stringify(log)); } catch (e) {}
  const panel = document.getElementById('ll-audit-panel');
  const body  = document.getElementById('ll-audit-body');

  const sev = (log.severity || '').toLowerCase();
  let sevClass = 'green';
  if (sev.includes('amber') || sev.includes('yellow')) sevClass = 'amber';
  else if (sev.includes('red')) sevClass = 'red';

  body.innerHTML = `
    <div class="ll-audit-sev-block">
      <div class="ll-audit-field-label">Severity</div>
      <div class="ll-sev-badge ll-sev-${sevClass}">${llEscapeHtml(log.severity || '—')}</div>
    </div>
    <div class="ll-audit-field">
      <div class="ll-audit-field-label">Expected Latency</div>
      <div class="ll-audit-field-value">${log.expected_latency_ms != null ? Number(log.expected_latency_ms).toFixed(2) + ' ms' : '—'}</div>
    </div>
    <div class="ll-audit-field">
      <div class="ll-audit-field-label">Delta</div>
      <div class="ll-audit-field-value ll-fv-${sevClass}">${log.delta_ms != null ? (log.delta_ms > 0 ? '+' : '') + Number(log.delta_ms).toFixed(2) + ' ms' : '—'}</div>
    </div>
    <div class="ll-audit-field">
      <div class="ll-audit-field-label">Delta %</div>
      <div class="ll-audit-field-value ll-fv-${sevClass}">${log.delta_pct != null ? (log.delta_pct > 0 ? '+' : '') + Number(log.delta_pct).toFixed(1) + '%' : '—'}</div>
    </div>
    <div class="ll-audit-field">
      <div class="ll-audit-field-label">Diagnosis Category</div>
      <div class="ll-audit-field-value" style="font-size:12px;">${llEscapeHtml(log.diagnosis_category || '—')}</div>
    </div>
    <div class="ll-audit-field ll-audit-wide">
      <div class="ll-audit-field-label">Recommended Action</div>
      <div class="ll-audit-field-value" style="font-size:12px;font-family:inherit;font-weight:400;color:var(--text);">${llEscapeHtml(log.recommended_action || '—')}</div>
    </div>
    <div class="ll-handoff-row">
      <button id="ll-handoff-btn" class="ll-btn ll-btn-secondary" onclick="pushToClarity()">
        &#x27A4; Push to Situation Intelligence Brief
      </button>
      <span id="ll-handoff-status" class="ll-handoff-status"></span>
    </div>
  `;
  panel.classList.add('visible');
  llAppendTranscript('[Audit log captured — scorecard updated]', 'system');
}

// ─── LL → CS Handoff (direct JS, no HTTP) ────────────────────────────────────
function normalizeLLPayload(raw) {
  const sevMap = { green: 'LOW', amber: 'MEDIUM', yellow: 'MEDIUM', red: 'CRITICAL' };
  const sevKey = String(raw.severity || '').toLowerCase().trim();
  return {
    severity:            sevMap[sevKey] || sevKey.toUpperCase() || 'UNKNOWN',
    expected_latency_ms: raw.expected_latency_ms || 0,
    delta_ms:            raw.delta_ms || 0,
    delta_pct:           raw.delta_pct,
    diagnosis_category:  raw.diagnosis_category || 'UNKNOWN',
    recommended_action:  raw.recommended_action || '',
    origin:              raw.origin || 'Unknown Origin',
    destination:         raw.destination || 'Unknown Destination',
    affected_services:   raw.affected_services || [],
    timestamp:           raw.timestamp || new Date().toISOString(),
  };
}

function pushToClarity() {
  if (!llLastAuditLog) return;
  if (llAutoPushTriggered && llPendingHandoff) return; // already pushed this session

  const btn      = document.getElementById('ll-handoff-btn');
  const statusEl = document.getElementById('ll-handoff-status');

  // Close Google Earth popup — no longer needed once we push to CS
  if (geWindowRef && !geWindowRef.closed) { geWindowRef.close(); geWindowRef = null; }

  // Capture Google Earth viewport from screen share if active
  const capture = captureScreenFrame();

  const normalized = normalizeLLPayload(llLastAuditLog);
  llPendingHandoff = normalized;
  try { localStorage.setItem('cs-last-handoff', JSON.stringify(normalized)); } catch (e) {}

  // Switch to CS, pre-fill viewport, then show banner
  switchPhase(2);

  if (capture) {
    _applyViewport(capture.data, capture.mime_type, capture.dataUrl);
    llAppendTranscript('[Google Earth screenshot captured and attached]', 'system');
  } else {
    // No active screen share — clear any stale viewport so CS starts clean
    clearViewport();
  }

  csShowHandoffBanner(normalized);

  if (btn) { btn.textContent = '✓ Sent to Situation Intelligence Brief'; btn.className = 'll-btn ll-btn-green'; btn.disabled = true; }
  if (statusEl) statusEl.textContent = '';
  llAppendTranscript('[Telemetry pushed to Situation Intelligence Brief]', 'system');

  // Auto-start generation — but wait for LL session to end first to avoid mic echo
  if (llSessionActive) {
    _csPendingAutoGenerate = true;  // will fire in llStopSession
  } else {
    csApplyHandoff(true);
  }
}

// ─── LL UI State ──────────────────────────────────────────────────────────────
function llSetStatus(state) {
  const cls   = (state === 'connected' || state === 'speaking') ? 'active' : '';
  const label = state === 'connected' ? 'Connected' : state === 'speaking' ? 'AI Speaking' : 'Disconnected';
  _llStatus = { cls, label };
  if (activePhase === 1) _applyStatus(cls, label);
}

function llSetMicActive(active) {
  const badge = document.getElementById('ll-mic-badge');
  badge.className = 'll-badge ' + (active ? 'll-badge-active-green' : 'll-badge-inactive');
}

function llSetScreenActive(active) {
  llScreenActive = active;
  const badge = document.getElementById('ll-screen-badge');
  badge.className = 'll-badge ' + (active ? 'll-badge-active-amber' : 'll-badge-inactive');
  const btn = document.getElementById('ll-screen-btn');
  if (active) {
    btn.className = 'll-btn ll-btn-amber';
    btn.innerHTML = '&#x274C; Stop Sharing';
  } else {
    btn.className = 'll-btn ll-btn-secondary';
    btn.innerHTML = '&#x1F5A5; Share Screen';
  }
}

function llSetAISpeaking(speaking) {
  llAISpeaking = speaking;
  const panel     = document.getElementById('ll-transcript-panel');
  const indicator = document.getElementById('ll-speaking-indicator');
  if (speaking) {
    panel.classList.add('ll-speaking');
    indicator.classList.remove('hidden');
    llSetStatus('speaking');
  } else {
    panel.classList.remove('ll-speaking');
    indicator.classList.add('hidden');
    if (llSessionActive) llSetStatus('connected');
  }
}

// ─── LL Button Handlers ───────────────────────────────────────────────────────
function llHandleSessionBtn() {
  if (!llSessionActive) llStartSession(); else llStopSession();
}
function llHandleScreenBtn() {
  if (!llScreenActive) llStartScreenShare(); else llStopScreenShare();
}
function llToggleTicket() {
  document.getElementById('ll-ticket-card').classList.toggle('ll-ticket-collapsed');
}

// ─── LL Session Management ────────────────────────────────────────────────────
async function llStartSession() {
  _dbgLog('p1', 'Starting LL session…', 'system');
  llSessionActive = true;
  const btn = document.getElementById('ll-session-btn');
  btn.className = 'll-btn ll-btn-red';
  btn.innerHTML = '&#9632; End Session';
  document.getElementById('ll-screen-btn').classList.remove('hidden');

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const llKey = getApiKey();
  const llWsUrl = `${protocol}://${location.host}/ws` + (llKey ? `?api_key=${encodeURIComponent(llKey)}` : '');
  llWs = new WebSocket(llWsUrl);

  llWs.onopen = () => {
    _dbgLog('p1', 'WS connected → /ws', 'system');
    llSetStatus('connected');
    llAppendTranscript('[Session started — Latency Lens Live is ready]', 'system');
  };
  llWs.onclose = () => {
    _dbgLog('p1', 'WS closed', 'system');
    llSetStatus('disconnected');
    llAppendTranscript('[Session closed]', 'system');
    llStopSession();
  };
  llWs.onerror = (e) => {
    _dbgLog('p1', `WS error: ${e.message || 'unknown'}`, 'error');
    llAppendTranscript('[WebSocket error — check console]', 'error');
  };
  llWs.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === 'audio') {
      llScheduleAudio(msg.data);
    } else if (msg.type === 'text') {
      llHandleText(msg.data);
    } else if (msg.type === 'interrupted') {
      llClearAudioQueue();
      llAppendTranscript('[AI interrupted — listening]', 'system');
    } else if (msg.type === 'error') {
      llAppendTranscript(`[ERROR: ${msg.message}]`, 'error');
    }
  };

  // Microphone
  try {
    llMicStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 48000 },
      video: false,
    });
    llCaptureCtx = new AudioContext();

    const workletCode = `
class PCMCapture extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;
    const samples = input[0];
    const ratio = sampleRate / 16000;
    const outLen = Math.floor(samples.length / ratio);
    if (outLen === 0) return true;
    const int16 = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const val = Math.max(-1, Math.min(1, samples[Math.min(Math.round(i * ratio), samples.length - 1)]));
      int16[i] = val < 0 ? val * 0x8000 : val * 0x7FFF;
    }
    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}
registerProcessor('pcm-capture', PCMCapture);
`;
    const blob = new Blob([workletCode], { type: 'application/javascript' });
    const url = URL.createObjectURL(blob);
    await llCaptureCtx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);

    const source = llCaptureCtx.createMediaStreamSource(llMicStream);
    llWorkletNode = new AudioWorkletNode(llCaptureCtx, 'pcm-capture');
    llWorkletNode.port.onmessage = (evt) => {
      if (llWs && llWs.readyState === WebSocket.OPEN) {
        llWs.send(JSON.stringify({ type: 'audio', data: llArrayBufferToBase64(evt.data) }));
      }
    };
    const silentGain = llCaptureCtx.createGain();
    silentGain.gain.value = 0;
    source.connect(llWorkletNode);
    llWorkletNode.connect(silentGain);
    silentGain.connect(llCaptureCtx.destination);
    llSetMicActive(true);
  } catch (err) {
    llAppendTranscript(`[Mic error: ${err.message}]`, 'error');
  }
}

function llStopSession() {
  llSessionActive = false;
  const _wasPushTriggered = llAutoPushTriggered || _csPendingAutoGenerate;
  llAutoPushTriggered = false;
  llStopScreenShare();

  if (_csPendingAutoGenerate) {
    // Push was triggered mid-session — fire generation now that session is ending
    _csPendingAutoGenerate = false;
    csApplyHandoff(true);
  } else if (llLastAuditLog && !_wasPushTriggered) {
    // Reliable fallback: session ended with an audit log but nothing pushed yet
    setTimeout(pushToClarity, 800);
  }

  if (llWorkletNode) { try { llWorkletNode.disconnect(); } catch (e) {} llWorkletNode = null; }
  if (llCaptureCtx)  { llCaptureCtx.close().catch(() => {}); llCaptureCtx = null; }
  if (llMicStream)   { llMicStream.getTracks().forEach(t => t.stop()); llMicStream = null; }
  if (llWs && llWs.readyState === WebSocket.OPEN) llWs.close();
  llWs = null;

  llClearAudioQueue();
  llSetMicActive(false);
  llSetScreenActive(false);
  llSetStatus('disconnected');

  const btn = document.getElementById('ll-session-btn');
  btn.className = 'll-btn ll-btn-green';
  btn.innerHTML = '&#9654; Start Session';
  document.getElementById('ll-screen-btn').classList.add('hidden');
}

// ─── LL Screen Share ──────────────────────────────────────────────────────────
async function llStartScreenShare() {
  try {
    llScreenStream = await navigator.mediaDevices.getDisplayMedia({
      video: { width: 1920, height: 1080 }, audio: false,
    });

    const video = document.createElement('video');
    video.srcObject = llScreenStream;
    video.muted = true;
    video.playsInline = true;
    video.style.cssText = 'position:fixed;width:1px;height:1px;opacity:0;pointer-events:none';
    document.body.appendChild(video);
    llScreenVideo = video;
    await video.play();

    const canvas = document.createElement('canvas');
    const ctx2d = canvas.getContext('2d');

    llScreenInterval = setInterval(() => {
      if (!llWs || llWs.readyState !== WebSocket.OPEN) return;
      if (!video.videoWidth) return;
      const scale = Math.min(1, 1024 / Math.max(video.videoWidth, video.videoHeight));
      const w = Math.floor(video.videoWidth * scale);
      const h = Math.floor(video.videoHeight * scale);
      canvas.width = w; canvas.height = h;
      ctx2d.drawImage(video, 0, 0, w, h);
      canvas.toBlob((blob) => {
        if (!blob) return;
        blob.arrayBuffer().then(buf => {
          if (llWs && llWs.readyState === WebSocket.OPEN) {
            llWs.send(JSON.stringify({ type: 'video', data: llArrayBufferToBase64(buf) }));
          }
        }).catch(err => console.error('[Screen capture encode error]', err));
      }, 'image/jpeg', 0.8);
    }, 1000);

    llScreenStream.getVideoTracks()[0].onended = () => llStopScreenShare();
    llSetScreenActive(true);
    llAppendTranscript('[Screen sharing started — AI can now see your viewport]', 'system');
  } catch (err) {
    if (err.name !== 'NotAllowedError') {
      llAppendTranscript(`[Screen share error: ${err.message}]`, 'error');
    }
  }
}

function llStopScreenShare() {
  clearInterval(llScreenInterval);
  llScreenInterval = null;
  if (llScreenVideo) { llScreenVideo.remove(); llScreenVideo = null; }
  if (llScreenStream) { llScreenStream.getTracks().forEach(t => t.stop()); llScreenStream = null; }
  llSetScreenActive(false);
  if (llSessionActive) llAppendTranscript('[Screen sharing stopped]', 'system');
}


// ═══════════════════════════════════════════════════════════════════════════════
//  PHASE 2 — CLARITY STUDIO
// ═══════════════════════════════════════════════════════════════════════════════

// ─── CS Audience Toggle ───────────────────────────────────────────────────────
let selectedAudience = 'CTO';

// ─── CS Grounding ─────────────────────────────────────────────────────────────
let csGroundingType = 'RAG';   // default: Aegius Benchmarking SLAs (Vertex AI RAG simulation)
let _csGroundingLabel = '';    // set from backend SSE grounding event

function csSetGrounding(type) {
  csGroundingType = type;
  document.getElementById('groundingRagInfo').style.display    = type === 'RAG'           ? 'block' : 'none';
  document.getElementById('groundingSearchInfo').style.display = type === 'GOOGLE_SEARCH' ? 'block' : 'none';
  document.getElementById('groundingSkillsInfo').style.display = type === 'SKILLS'        ? 'block' : 'none';
  document.getElementById('groundingExtraCtx').style.display   = type === 'EXTRA_CONTEXT' ? 'block' : 'none';
  _dbgLog('p2', `Grounding set: ${type}`, 'system');
}

document.querySelectorAll('.toggle-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedAudience = btn.dataset.value;
  });
});

// ─── CS Audio Engine (Gemini SSE audio) ──────────────────────────────────────
let csAudioMuted = false;
let csAudioCtx = null;
let csNextAudioTime = 0;
let csHasNativeAudio = false;

function csEnsureAudioCtx() {
  if (!csAudioCtx) {
    csAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    csNextAudioTime = csAudioCtx.currentTime;
  }
  if (csAudioCtx.state === 'suspended') csAudioCtx.resume();
}

async function csPlayAudioChunk(base64data, mimeType) {
  if (csAudioMuted) return;
  csEnsureAudioCtx();
  const rateMatch = mimeType.match(/rate=(\d+)/i);
  const sampleRate = rateMatch ? parseInt(rateMatch[1], 10) : 24000;
  const binary = atob(base64data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const int16 = new Int16Array(bytes.buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;
  const buffer = csAudioCtx.createBuffer(1, float32.length, sampleRate);
  buffer.getChannelData(0).set(float32);
  const source = csAudioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(csAudioCtx.destination);
  const startAt = Math.max(csNextAudioTime, csAudioCtx.currentTime + 0.05);
  source.start(startAt);
  csNextAudioTime = startAt + buffer.duration;
}

function toggleAudio() {
  csAudioMuted = !csAudioMuted;
  document.getElementById('audioToggle').textContent = csAudioMuted ? 'Unmute' : 'Mute';
  if (csAudioMuted && window.speechSynthesis) window.speechSynthesis.cancel();
}

function csSpeakNarration(text) {
  if (csAudioMuted || csHasNativeAudio || !window.speechSynthesis || llSessionActive) return;
  const clean = text.replace(/\*\*/g, '').replace(/\*/g, '').replace(/`/g, '').trim();
  if (!clean) return;
  // Capture which frame card this narration belongs to (csCurrentFrameBody may change by the time it speaks)
  const card = csCurrentFrameBody?.closest('.frame-card') ?? null;
  const utt = new SpeechSynthesisUtterance(clean);
  utt.rate = 0.95; utt.pitch = 1.0; utt.volume = 0.9;
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Google') || v.name.includes('Natural')))
    || voices.find(v => v.lang.startsWith('en'));
  if (preferred) utt.voice = preferred;
  utt.onstart = () => {
    if (card) {
      card.classList.remove('frame-pending');
      card.classList.add('frame-active');
      _csAutoScroll = true;
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      const idx = _csFrameCards.indexOf(card);
      if (idx >= 0) _csCurrentSlideIndex = idx;

    }
    document.getElementById('audioLabel').textContent = 'Narration Active';
    document.getElementById('audioPauseBtn').textContent = '⏸ Pause';
  };
  utt.onend = () => {
    if (!window.speechSynthesis.speaking) {
      document.getElementById('audioLabel').textContent = 'Narration Done';
    }
  };
  window.speechSynthesis.speak(utt);
}

function csPauseResume() {
  if (window.speechSynthesis.paused) {
    window.speechSynthesis.resume();
    document.getElementById('audioPauseBtn').textContent = '⏸ Pause';
    document.getElementById('audioLabel').textContent = 'Narration Active';
  } else {
    window.speechSynthesis.pause();
    document.getElementById('audioPauseBtn').textContent = '▶ Resume';
    document.getElementById('audioLabel').textContent = 'Paused';
  }
}

function csStopNarration() {
  window.speechSynthesis.cancel();
  document.getElementById('audioPauseBtn').textContent = '⏸ Pause';
  document.getElementById('audioLabel').textContent = 'Stopped';
}

function csPrevSlide() {
  const cards = _csFrameCards.filter(c => c.classList.contains('frame-active'));
  const visibleIdx = cards.indexOf(_csFrameCards[_csCurrentSlideIndex]);
  if (visibleIdx > 0) {
    _csCurrentSlideIndex = _csFrameCards.indexOf(cards[visibleIdx - 1]);
    cards[visibleIdx - 1].scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function csNextSlide() {
  const cards = _csFrameCards.filter(c => c.classList.contains('frame-active'));
  const visibleIdx = cards.indexOf(_csFrameCards[_csCurrentSlideIndex]);
  if (visibleIdx < cards.length - 1) {
    _csCurrentSlideIndex = _csFrameCards.indexOf(cards[visibleIdx + 1]);
    cards[visibleIdx + 1].scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function csShowAudioBar() {
  document.getElementById('audioBar').style.display = 'flex';
  cs2SetNarrating(true);
}

// ─── CS Status ────────────────────────────────────────────────────────────────
function csSetStatus(state, label) {
  _csStatus = { cls: state || '', label };
  if (activePhase === 2) _applyStatus(state || '', label);
}

function cs2SetNarrating(on) {
  document.getElementById('cs-narrating-indicator')?.classList.toggle('hidden', !on);
}

function cs2SetGenerating(on) {
  document.getElementById('cs-listening-indicator')?.classList.toggle('hidden', !on);
}

// ─── CS Viewport ──────────────────────────────────────────────────────────────
let viewportImageData = null;
let viewportImageSrc  = null;

function _applyViewport(b64data, mimeType, dataUrl) {
  viewportImageData = { mime_type: mimeType, data: b64data };
  viewportImageSrc  = dataUrl;
}

function onViewportFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    const [header, b64] = dataUrl.split(',');
    const mimeMatch = header.match(/:(.*?);/);
    _applyViewport(b64, mimeMatch ? mimeMatch[1] : 'image/jpeg', dataUrl);
  };
  reader.readAsDataURL(file);
}

/** Capture the current frame from the LL screen share as a JPEG. Returns null if inactive. */
function captureScreenFrame() {
  if (!llScreenVideo || !llScreenVideo.videoWidth) return null;
  const canvas = document.createElement('canvas');
  const scale  = Math.min(1, 1280 / Math.max(llScreenVideo.videoWidth, llScreenVideo.videoHeight));
  canvas.width  = Math.floor(llScreenVideo.videoWidth  * scale);
  canvas.height = Math.floor(llScreenVideo.videoHeight * scale);
  canvas.getContext('2d').drawImage(llScreenVideo, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
  return { mime_type: 'image/jpeg', data: dataUrl.split(',')[1], dataUrl };
}

function clearViewport() {
  viewportImageData = null;
  viewportImageSrc  = null;
}

// ─── CS Stream State ──────────────────────────────────────────────────────────
let csStreamBuffer = '';
let csFrameCount = 0;
let csOutputContainer;
let csAbortController = null;
let _csFrameCards = [];
let _csCurrentSlideIndex = 0;

// ─── CS Storyboard Rendering ──────────────────────────────────────────────────
function csCreateFrameCard(number, title) {
  const card = document.createElement('div');
  // Numbered frames start hidden; system-log (●) shows immediately
  const isPending = /^\d+$/.test(String(number));
  card.className = 'frame-card' + (isPending ? ' frame-pending' : ' frame-active');
  card.id = `frame-${number}`;
  const header = document.createElement('div');
  header.className = 'frame-card-header';
  header.innerHTML = `<div class="frame-number">${number}</div><span>${title}</span>`;
  const body = document.createElement('div');
  body.className = 'frame-card-body';
  body.id = `frame-body-${number}`;
  card.appendChild(header);
  card.appendChild(body);
  csOutputContainer.appendChild(card);
  _csFrameCards.push(card);
  return body;
}

function csRenderSystemLog(text) {
  const body = csCreateFrameCard('●', 'System Log');
  const log = document.createElement('div');
  log.className = 'system-log';
  log.textContent = text.replace('[SYSTEM LOG]', '').trim();
  body.appendChild(log);
  return body;
}

function csRenderNarratorBlock(text) {
  const div = document.createElement('div');
  div.className = 'narrator-block';
  div.innerHTML = `<span class="narrator-icon">🎙</span><span class="narrator-text">${csEscapeHtml(text)}</span>`;
  return div;
}


function csAddPreLastSlideImage() {
  // Find numbered frame cards (id="frame-1", "frame-2" etc.)
  const cards = Array.from(document.querySelectorAll('.frame-card')).filter(
    c => /^frame-\d+$/.test(c.id)
  );
  if (cards.length < 2) return;
  const preLastCard = cards[cards.length - 2];
  // Skip if already has an image frame
  if (preLastCard.querySelector('.video-ge-frame')) return;
  const body = preLastCard.querySelector('.frame-card-body');
  if (!body) return;
  // Collect text from narrator + any plain text nodes in this card
  const narText = Array.from(body.querySelectorAll('.narrator-text'))
    .map(el => el.textContent).join(' ').trim();
  const frameTitle = preLastCard.querySelector('.frame-card-header span')?.textContent || 'Recommendation';
  const imgWrap = document.createElement('div');
  imgWrap.className = 'video-player';
  imgWrap.style.marginTop = '12px';
  const imgHeader = document.createElement('div');
  imgHeader.className = 'video-ge-header';
  imgHeader.innerHTML = `<span class="video-tag">🖼 AI IMAGE</span><span class="video-label">${frameTitle.toUpperCase()}</span>`;
  const imgFrame = document.createElement('div');
  imgFrame.className = 'video-ge-frame';
  imgWrap.appendChild(imgHeader);
  imgWrap.appendChild(imgFrame);
  body.appendChild(imgWrap);
  _nanoBananaFetch(_nanoBananaPrompt(frameTitle, narText), imgFrame, frameTitle, preLastCard);
}

function csAddGroundingBadge() {
  if (csGroundingType === 'NONE') return;
  const cards = Array.from(document.querySelectorAll('.frame-card')).filter(
    c => /^frame-\d+$/.test(c.id)
  );
  if (cards.length < 2) return;
  const preLastCard = cards[cards.length - 2];
  if (preLastCard.querySelector('.grounding-badge')) return;
  const label = _csGroundingLabel || csGroundingType;
  const icons = { RAG: '📄', GOOGLE_SEARCH: '🔍', SKILLS: '⚙️', EXTRA_CONTEXT: '📎' };
  const ragLabel = 'Aegius Benchmarking SLAs · Vertex AI RAG (simulated)';
  const displayLabel = csGroundingType === 'RAG' ? ragLabel : (label || csGroundingType);
  const icon = icons[csGroundingType] || '◈';
  const badge = document.createElement('div');
  badge.className = 'grounding-badge';
  badge.innerHTML = `${icon} Grounded via <strong>${displayLabel}</strong>`;
  const body = preLastCard.querySelector('.frame-card-body');
  if (body) body.appendChild(badge);
}

// ─── Nano Banana helpers ──────────────────────────────────────────────────────
function _nanoBananaPrompt(scene, narratorCtx) {
  return `Professional executive briefing slide illustration.
Scene: ${scene}
Narrator context: ${narratorCtx || 'Fiber optic network route mismatch on SFO to PHX corridor'}
Main topic: Fiber optic telecommunications infrastructure. Route mismatch: traffic incorrectly routed over Sierra Nevada mountains instead of following I-10 Southern Corridor (SFO → LA → PHX).
Style: photorealistic satellite or aerial view, dark tech aesthetic, blue tones, no text overlays, suitable for C-suite presentation.`;
}

// card: nearest .frame-card ancestor to hold as frame-pending until image resolves
function _nanoBananaFetch(prompt, mapDiv, altText, card) {
  _dbgLog('p2', `Nano Banana: "${prompt.slice(0, 100)}…"`, 'info');
  mapDiv.innerHTML = '<div class="cs-spinner" style="margin:auto"></div>';
  // Hold the card in pending state while fetching
  if (card) card.classList.replace('frame-active', 'frame-pending');
  const apiKey = getApiKey();
  fetch('/generate-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, api_key: apiKey || null }),
  })
    .then(r => r.ok ? r.json() : r.text().then(t => Promise.reject(`HTTP ${r.status}: ${t}`)))
    .then(data => {
      _dbgLog('p2', `Nano Banana image received (${data.mime_type})`, 'info');
      const img = document.createElement('img');
      img.style.cssText = 'width:100%;height:100%;object-fit:contain;border-radius:6px';
      img.src = `data:${data.mime_type};base64,${data.image}`;
      img.alt = altText || 'Generated slide illustration';
      mapDiv.innerHTML = '';
      mapDiv.appendChild(img);
    })
    .catch(err => {
      _dbgLog('p2', `Nano Banana failed: ${err} — falling back to wrong_path.png`, 'warn');
      const img = document.createElement('img');
      img.style.cssText = 'width:100%;height:100%;object-fit:contain;border-radius:6px';
      img.src = 'wrong_path.png';
      img.alt = altText || 'Slide illustration';
      mapDiv.innerHTML = '';
      mapDiv.appendChild(img);
    })
    .finally(() => {
      if (card) card.classList.replace('frame-pending', 'frame-active');
    });
}

function csRenderVideoPlayer(tag) {
  const label = tag.replace('[PLAY VIDEO:', '').replace(']', '').trim();
  const wrap = document.createElement('div');
  wrap.className = 'video-player';

  const header = document.createElement('div');
  header.className = 'video-ge-header';
  header.innerHTML = `<span class="video-tag">🖼 AI IMAGE</span><span class="video-label">${csEscapeHtml(label.replace(/_/g, ' ').toUpperCase())}</span>`;
  wrap.appendChild(header);

  const mapDiv = document.createElement('div');
  mapDiv.className = 'video-ge-frame';
  wrap.appendChild(mapDiv);

  const ge = _csLastGECoords;
  if (ge) {
    const btn = document.createElement('button');
    btn.className = 'll-btn-ge video-ge-btn';
    btn.textContent = 'Open in Google Earth ↗';
    btn.onclick = () => openGoogleEarth(ge.la, ge.lo, ge.di);
    wrap.appendChild(btn);
  }

  // Capture narrator context at call time (may change as more lines stream in)
  const narratorCtx = csLastNarratorText;
  const frameLabel = label.replace(/_/g, ' ');
  const imagePrompt = _nanoBananaPrompt(frameLabel, narratorCtx);
  const card = wrap.closest?.('.frame-card') ?? csCurrentFrameBody?.closest('.frame-card');
  _nanoBananaFetch(imagePrompt, mapDiv, frameLabel, card);

  return wrap;
}

function csSanitizeMermaid(src) {
  // Remove problem directive lines
  src = src.replace(/^\s*(linkStyle|classDef|style)\s+.*$/gm, '');
  // Fix quoted labels: collapse internal newlines, strip --> which breaks the lexer
  src = src.replace(/"([^"]*)"/g, (_, inner) =>
    `"${inner.replace(/\s*\n\s*/g, ' ').replace(/-->/g, '→').replace(/[()]/g, '')}"`
  );
  // Wrap unquoted square-bracket labels that contain special chars in quotes
  src = src.replace(/\[([^\]"]+)\]/g, (match, inner) => {
    if (/[()[\]<>\/\\]/.test(inner) || /\n/.test(inner)) {
      const clean = inner.replace(/[()[\]<>\/\\]/g, '').replace(/\s*\n\s*/g, ' ').replace(/"/g, "'").trim();
      return `["${clean}"]`;
    }
    return match;
  });
  return src.trim();
}

async function csRenderMermaid(diagramSource, container) {
  const wrap = document.createElement('div');
  wrap.className = 'diagram-wrap';
  container.appendChild(wrap);
  try {
    const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const { svg } = await mermaid.render(id, csSanitizeMermaid(diagramSource));
    wrap.innerHTML = svg;
  } catch (err) {
    console.warn('Mermaid render error:', err);
    wrap.innerHTML = `<pre style="color:#94a3b8;font-size:11px;text-align:left">${csEscapeHtml(diagramSource)}</pre>`;
  }

  // Add a Nano Banana repainted visual below the diagram for readability
  const diagramDesc = diagramSource.replace(/```/g, '').trim().slice(0, 400);
  const prompt = _nanoBananaPrompt(
    `Data flow / network diagram visualization: ${diagramDesc}`,
    csLastNarratorText
  );
  const imgWrap = document.createElement('div');
  imgWrap.className = 'video-player';
  imgWrap.style.marginTop = '12px';
  const imgHeader = document.createElement('div');
  imgHeader.className = 'video-ge-header';
  imgHeader.innerHTML = '<span class="video-tag">🖼 AI IMAGE</span><span class="video-label">DIAGRAM VISUALIZATION</span>';
  const imgFrame = document.createElement('div');
  imgFrame.className = 'video-ge-frame';
  imgWrap.appendChild(imgHeader);
  imgWrap.appendChild(imgFrame);
  container.appendChild(imgWrap);
  const mermaidCard = container.closest('.frame-card');
  _nanoBananaFetch(prompt, imgFrame, 'Diagram visualization', mermaidCard);
}

function csRenderScorecard(text) {
  const div = document.createElement('div');
  const level = text.includes('🔴') ? 'red' : text.includes('🟡') ? 'amber' : 'green';
  div.className = `scorecard ${level}`;
  const lines = text.split('\n').filter(l => l.trim());
  const title = lines[0].replace(/\[|\]/g, '').trim();
  const body = lines.slice(1).join('\n');
  div.innerHTML = `
    <div class="scorecard-title">${csEscapeHtml(title)}</div>
    <div class="scorecard-body">${csParseInlineMarkdown(body)}</div>
  `;
  return div;
}

function csRenderJiraCard(text) {
  const div = document.createElement('div');
  div.className = 'jira-card';
  // Extract a URL from the ticket text if present
  const urlMatch = text.match(/https?:\/\/[^\s\)\"]+/);
  const approveHtml = urlMatch
    ? `<a class="jira-approve-btn" href="${urlMatch[0]}" target="_blank" rel="noopener">✓ Approve in Jira ↗</a>`
    : `<button class="jira-approve-btn" onclick="csSimulateJiraApprove(this)">✓ Approve Ticket</button>`;
  div.innerHTML = `
    <div class="jira-header">
      <span><span class="jira-icon">🎫</span> Jira Ticket — Emergency Action</span>
      ${approveHtml}
    </div>
    <div class="jira-body">${csEscapeHtml(text)}</div>
  `;
  return div;
}

function csSimulateJiraApprove(btn) {
  btn.textContent = '✓ Approved';
  btn.style.background = 'var(--green, #22c55e)';
  btn.style.borderColor = 'var(--green, #22c55e)';
  btn.style.color = '#fff';
  btn.disabled = true;
  // Approval triggers the handoff to Circuit Stitcher
  pushToCS3();
}

function csRenderBullets(lines) {
  const ul = document.createElement('ul');
  ul.className = 'bullet-list';
  lines.forEach(line => {
    const li = document.createElement('li');
    li.innerHTML = csParseInlineMarkdown(line.replace(/^[-*•▸]\s*/, '').trim());
    ul.appendChild(li);
  });
  return ul;
}

function csRenderTextContent(text) {
  const div = document.createElement('div');
  div.className = 'text-content';
  div.innerHTML = csParseInlineMarkdown(text);
  return div;
}

function csParseInlineMarkdown(text) {
  return csEscapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br/>');
}

function csEscapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── CS Stream Parser ─────────────────────────────────────────────────────────
let csInMermaidBlock = false;
let csMermaidLines = [];
let csInCodeBlock = false;
let csCodeBlockLines = [];
let csInScorecardBlock = false;
let csScorecardLines = [];
let csCurrentFrame = null;
let csCurrentFrameBody = null;
let csMermaidContainer = null;
let csLastNarratorText = '';   // tracks latest narrator line — used for image prompts

const CS_FRAME_PATTERNS = [
  { re: /\[Frame 1/i, title: 'Observation — The Video',     num: 1 },
  { re: /\[Frame 2/i, title: 'Explanation — The Diagram',   num: 2 },
  { re: /\[Frame 3/i, title: 'Implication — The Scorecard', num: 3 },
  { re: /\[Frame 4/i, title: 'Execution Payload',            num: 4 },
];

const GE_OPEN_RE = /\[GE_OPEN:([-\d.]+),([-\d.]+),([\d.]+)\]/g;
let _csLastGECoords = null;
let _csRouteCoords = null;  // { lat1, lon1, lat2, lon2 } from ROUTE_COORDS tag
let _csTelemetryOrigin = '';
let _csTelemetryDest = '';
const ROUTE_COORDS_RE = /\[ROUTE_COORDS:([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\]/g;

function csProcessBuffer() {
  const lines = csStreamBuffer.split('\n');
  const completeLines = lines.slice(0, -1);
  csStreamBuffer = lines[lines.length - 1];
  for (const rawLine of completeLines) csProcessLine(rawLine);
}

function csFlushScorecard() {
  if (!csScorecardLines.length) return;
  const el = csRenderScorecard(csScorecardLines.join('\n'));
  (csCurrentFrameBody || csOutputContainer).appendChild(el);
  csScorecardLines = [];
  csInScorecardBlock = false;
}

function csProcessLine(line) {
  // Handle GE_OPEN: stash coords only (video player renders the map + single button)
  line = line.replace(GE_OPEN_RE, (_, lat, lon, dist) => {
    _csLastGECoords = { la: parseFloat(lat), lo: parseFloat(lon), di: parseFloat(dist) };
    return '';
  });
  // Handle ROUTE_COORDS: stash endpoint coords for Leaflet map
  line = line.replace(ROUTE_COORDS_RE, (_, la1, lo1, la2, lo2) => {
    _csRouteCoords = { lat1: parseFloat(la1), lon1: parseFloat(lo1), lat2: parseFloat(la2), lon2: parseFloat(lo2) };
    return '';
  });
  const trimmed = line.trim();

  if (trimmed.startsWith('```mermaid')) {
    csInMermaidBlock = true;
    csMermaidLines = [];
    csMermaidContainer = csCurrentFrameBody || csOutputContainer;
    return;
  }
  if (csInMermaidBlock) {
    if (trimmed === '```') {
      csInMermaidBlock = false;
      csRenderMermaid(csMermaidLines.join('\n'), csMermaidContainer);
      csMermaidLines = [];
    } else {
      csMermaidLines.push(line);
    }
    return;
  }
  if (trimmed.startsWith('```') && !csInCodeBlock) {
    csInCodeBlock = true; csCodeBlockLines = []; return;
  }
  if (csInCodeBlock) {
    if (trimmed === '```') {
      csInCodeBlock = false;
      const content = csCodeBlockLines.join('\n');
      const target = csCurrentFrameBody || csOutputContainer;
      if (csCurrentFrame === 4) {
        target.appendChild(csRenderJiraCard(content));
      } else {
        const pre = document.createElement('pre');
        pre.style.cssText = 'background:#0d1b2a;border:1px solid #1e3a5f;border-radius:8px;padding:12px;font-size:12px;color:#94a3b8;overflow-x:auto;';
        pre.textContent = content;
        target.appendChild(pre);
      }
      csCodeBlockLines = [];
    } else {
      csCodeBlockLines.push(line);
    }
    return;
  }
  if (csInScorecardBlock) {
    if (!trimmed || CS_FRAME_PATTERNS.some(p => p.re.test(line)) || line.includes('[SYSTEM LOG]')) {
      csFlushScorecard();
    } else {
      csScorecardLines.push(line); return;
    }
  }
  if (line.includes('[SYSTEM LOG]')) {
    const body = csRenderSystemLog(line);
    csFrameCount++;
    csUpdateFrameCounter();
    csCurrentFrameBody = body; return;
  }
  for (const pat of CS_FRAME_PATTERNS) {
    if (pat.re.test(line)) {
      csCurrentFrame = pat.num;
      csCurrentFrameBody = csCreateFrameCard(pat.num, pat.title);
      csFrameCount++;
      csUpdateFrameCounter();
      return;
    }
  }
  const narratorMatch = line.match(/^(?:Narrator Voice:|narrator voice:)\s*(.+)/i);
  if (narratorMatch) {
    const narText = narratorMatch[1].replace(/^\(|\)$/g, '').trim();
    csLastNarratorText = narText;
    (csCurrentFrameBody || csOutputContainer).appendChild(csRenderNarratorBlock(narText));
    csSpeakNarration(narText);
    csShowAudioBar();
    return;
  }
  if (line.includes('[PLAY VIDEO:')) {
    (csCurrentFrameBody || csOutputContainer).appendChild(csRenderVideoPlayer(line));
    return;
  }
  if (/SEVERITY ALARM|🔴|🟡|🟢/.test(line) && /ALARM|SEVERITY/i.test(line)) {
    csInScorecardBlock = true; csScorecardLines = [line]; return;
  }
  if (/^[-*•▸]\s/.test(trimmed)) {
    (csCurrentFrameBody || csOutputContainer).appendChild(csRenderBullets([trimmed]));
    return;
  }
  if (!trimmed || /^---+$/.test(trimmed) || /^===+$/.test(trimmed)) return;
  (csCurrentFrameBody || csOutputContainer).appendChild(csRenderTextContent(trimmed));
}

function csUpdateFrameCounter() {
  const el = document.getElementById('frameCounter');
  if (el) el.textContent = `${csFrameCount} frame${csFrameCount !== 1 ? 's' : ''}`;
}

// ─── CS Sample Data ───────────────────────────────────────────────────────────
const CS_SAMPLES = [
  {
    severity: 'CRITICAL', circuit_id: 'C2891-W-SFO-PHX', fiber_route_km: 1200,
    expected_latency_ms: 11.1, measured_latency_ms: 15.2, delta_ms: 4.1, delta_pct: 36.9,
    diagnosis_category: 'ROUTE_MISMATCH',
    recommended_action: 'Execute collaborative reroute via Southern Corridor (Motorway I-10) using Circuit Stitcher.',
    origin: 'SFO (San Francisco)', origin_lat: 37.6213, origin_lon: -122.3790,
    destination: 'PHX (Phoenix)', destination_lat: 33.4373, destination_lon: -112.0078,
    affected_services: ['cdn-edge', 'video-streaming', 'api-gateway'],
    timestamp: '2026-03-15T14:07:09Z',
  },
  {
    severity: 'CRITICAL', expected_latency_ms: 45, delta_ms: 312, delta_pct: 693,
    diagnosis_category: 'BGP_ROUTE_FLAP',
    recommended_action: 'Engage transit providers; audit BGP peering configs for us-west-2 ↔ eu-central-1.',
    origin: 'us-west-2 (Oregon)', origin_lat: 45.52, origin_lon: -122.68,
    destination: 'eu-central-1 (Frankfurt)', destination_lat: 50.11, destination_lon: 8.68,
    affected_services: ['payment-gateway', 'order-service', 'real-time-analytics'],
    timestamp: '2026-03-14T09:42:17Z',
  },
  {
    severity: 'MEDIUM', expected_latency_ms: 80, delta_ms: 55, delta_pct: 69,
    diagnosis_category: 'FIBER_CUT',
    recommended_action: 'Activate backup dark fiber on Ring-B; dispatch field crew to Mile 142.',
    origin: 'ap-southeast-1 (Singapore)', destination: 'ap-northeast-1 (Tokyo)',
    affected_services: ['trading-platform', 'market-data-feed'],
    timestamp: new Date().toISOString(),
  },
];
let _sampleIdx = 0;

function csLoadSample() {
  const s = CS_SAMPLES[_sampleIdx % CS_SAMPLES.length];
  _sampleIdx++;
  document.getElementById('telemetryInput').value = JSON.stringify(s, null, 2);
}

// ─── CS Handoff Banner ────────────────────────────────────────────────────────
function csShowHandoffBanner(payload) {
  const banner = document.getElementById('handoffBanner');
  const meta   = document.getElementById('handoffMeta');
  meta.textContent = `${payload.severity || ''} · ${payload.diagnosis_category || ''}`;
  banner.style.display = 'flex';
}

function csDismissHandoff() {
  document.getElementById('handoffBanner').style.display = 'none';
  llPendingHandoff = null;
}

function csTogglePayload() {
  const grp = document.getElementById('telemetryGroup');
  const btn = document.getElementById('csPayloadToggle');
  if (!grp) return;
  const visible = grp.style.display !== 'none';
  grp.style.display = visible ? 'none' : 'flex';
  if (btn) btn.textContent = (visible ? '▸' : '▾') + ' ' + (visible ? 'Show' : 'Hide') + ' telemetry payload';
}

function csApplyHandoff(auto = false) {
  if (!llPendingHandoff) return;
  _dbgLog('p2', `Applying handoff from Phase 1: ${JSON.stringify(llPendingHandoff).slice(0,120)}…`, 'system');
  document.getElementById('telemetryInput').value = JSON.stringify(llPendingHandoff, null, 2);
  if (!auto) document.getElementById('handoffBanner').style.display = 'none';
  startBriefing(auto);
  llPendingHandoff = null;
}

// ─── CS Clear ─────────────────────────────────────────────────────────────────
function clearOutput() {
  if (csAbortController) csAbortController.abort();
  csOutputContainer.innerHTML = `
    <div class="empty-state" id="emptyState">
      <div class="empty-icon">◈</div>
      <p>Awaiting results from Latency Lens…</p>
      <p class="empty-sub">Powered by Gemini 2.5 Flash · Interleaved Multimodal Generation</p>
    </div>
  `;
  csStreamBuffer = '';
  csFrameCount = 0;
  csCurrentFrameBody = null;
  csCurrentFrame = null;
  csInMermaidBlock = false; csMermaidLines = [];
  csInCodeBlock = false; csCodeBlockLines = [];
  csInScorecardBlock = false; csScorecardLines = [];
  csLastNarratorText = '';
  _csGroundingLabel = '';
  csHasNativeAudio = false;
  csNextAudioTime = 0;
  csUpdateFrameCounter();
  csSetStatus('', 'Standby');
  document.getElementById('audioBar').style.display = 'none';
  document.getElementById('generateBtn').disabled = false;
  const pushBtn = document.getElementById('pushToCS3Btn');
  if (pushBtn) pushBtn.style.display = 'none';
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  if (geWindowRef && !geWindowRef.closed) geWindowRef.close();
  geWindowRef = null;
}

// ─── CS Generate Briefing ─────────────────────────────────────────────────────
async function startBriefing(fromHandoff = false) {
  _dbgLog('p2', `startBriefing(fromHandoff=${fromHandoff})`, 'system');
  let telemetry;
  try {
    telemetry = JSON.parse(document.getElementById('telemetryInput').value);
  } catch {
    _dbgLog('p2', 'Invalid JSON in telemetry payload', 'error');
    alert('Invalid JSON in telemetry payload.');
    return;
  }
  _dbgLog('p2', `Telemetry: circuit=${telemetry.circuit_id} sev=${telemetry.severity} delta=${telemetry.delta_pct}%`, 'info');
  _csTelemetryOrigin = telemetry.origin || '';
  _csTelemetryDest   = telemetry.destination || '';

  const backendUrl = `${location.protocol}//${location.host}`;
  clearOutput();
  const emptyState = document.getElementById('emptyState');
  if (emptyState) {
    emptyState.querySelector('.empty-icon').innerHTML = '<div class="cs-spinner"></div>';
    emptyState.querySelector('p').textContent = 'Generating executive briefing…';
    emptyState.querySelector('.empty-sub').textContent = 'Powered by Gemini 2.5 Flash';
  }
  document.getElementById('generateBtn').disabled = true;
  csOutputContainer = document.getElementById('outputContainer');
  csStreamBuffer = '';
  csFrameCount = 0;
  csCurrentFrameBody = null;
  csCurrentFrame = null;
  csInMermaidBlock = false; csMermaidLines = [];
  csInCodeBlock = false; csCodeBlockLines = [];
  csInScorecardBlock = false; csScorecardLines = [];
  csHasNativeAudio = false;
  csNextAudioTime = 0;
  _csLastGECoords = null;
  _csRouteCoords = null;
  _csTelemetryOrigin = '';
  _csTelemetryDest = '';
  _csFrameCards = [];
  _csCurrentSlideIndex = 0;
  _csAutoScroll = true;
  csSetStatus('active', 'Generating...');
  cs2SetGenerating(true);
  csAbortController = new AbortController();

  try {
    const body = { telemetry, audience_type: selectedAudience, grounding_type: csGroundingType };
    if (viewportImageData) body.viewport_image = viewportImageData;
    if (csGroundingType === 'EXTRA_CONTEXT') {
      body.extra_context = document.getElementById('groundingExtraCtx').value || '';
    }
    if (csGroundingType !== 'NONE') {
      _dbgLog('p2', `Grounding active: ${csGroundingType}`, 'info');
    }
    _csGroundingLabel = '';
    const apiKey = getApiKey();
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/generate-briefing`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: csAbortController.signal,
    });
    if (!res.ok) {
      throw new Error(`Backend error ${res.status}: ${await res.text()}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      const events = sseBuffer.split('\n\n');
      sseBuffer = events.pop();

      for (const event of events) {
        if (!event.startsWith('data: ')) continue;
        const raw = event.slice(6).trim();
        if (!raw) continue;
        let msg;
        try { msg = JSON.parse(raw); } catch { continue; }

        if (msg.type === 'audio' && msg.data) {
          csHasNativeAudio = true;
          csShowAudioBar();
          csPlayAudioChunk(msg.data, msg.mime_type || 'audio/pcm;rate=24000');
        } else if (msg.type === 'chunk' && msg.text) {
          document.getElementById('emptyState')?.remove();
          document.getElementById('handoffBanner').style.display = 'none';
          csStreamBuffer += msg.text;
          csProcessBuffer();
        } else if (msg.type === 'grounding') {
          _csGroundingLabel = msg.label || msg.mode;
          _dbgLog('p2', `Grounding active: ${msg.mode} — ${msg.label}`, 'info');
        } else if (msg.type === 'error') {
          csSetStatus('error', 'Error');
          const errDiv = document.createElement('div');
          errDiv.style.cssText = 'color:#ef4444;padding:12px;font-family:monospace;font-size:12px;background:#1a0a0a;border-radius:8px;border:1px solid #ef444440;';
          errDiv.textContent = `Error: ${msg.message}`;
          csOutputContainer.appendChild(errDiv);
        } else if (msg.type === 'end') {
          if (csStreamBuffer.trim()) { csStreamBuffer += '\n'; csProcessBuffer(); }
        }
      }
    }

    if (csStreamBuffer.trim()) { csStreamBuffer += '\n'; csProcessBuffer(); }
    csFlushScorecard();
    csAddPreLastSlideImage();
    csAddGroundingBadge();
    csSetStatus('', 'Complete');
    csShowReplayBtn();
    const pushBtn = document.getElementById('pushToCS3Btn');
    if (pushBtn) pushBtn.style.display = '';
  } catch (err) {
    if (err.name === 'AbortError') {
      csSetStatus('', 'Cancelled');
    } else {
      csSetStatus('error', 'Error');
      console.error(err);
      const errDiv = document.createElement('div');
      errDiv.style.cssText = 'color:#ef4444;padding:12px;font-family:monospace;font-size:12px;background:#1a0a0a;border-radius:8px;border:1px solid #ef444440;margin:8px 0;';
      errDiv.textContent = `Connection error: ${err.message}`;
      csOutputContainer.appendChild(errDiv);
    }
  } finally {
    document.getElementById('generateBtn').disabled = false;
    cs2SetGenerating(false);
    csHideAudioBarWhenDone();
  }
}

function csShowReplayBtn() {
  const existing = document.getElementById('replayBtn');
  if (existing) return;
  const btn = document.createElement('button');
  btn.id = 'replayBtn';
  btn.className = 'replay-btn';
  btn.innerHTML = '↺ Replay Narration';
  btn.onclick = () => {
    window.speechSynthesis.cancel();
    _csFrameCards.forEach(card => {
      card.classList.remove('frame-active');
      card.classList.add('frame-pending');
    });
    _csCurrentSlideIndex = 0;
    // Re-queue all narrations by re-triggering csSpeakNarration for each frame's narrator block
    document.querySelectorAll('.narrator-text').forEach((el, i) => {
      const card = el.closest('.frame-card');
      if (card) {
        const text = el.textContent;
        // Re-speak with card context
        const utt = new SpeechSynthesisUtterance(text);
        utt.rate = 0.95; utt.pitch = 1.0; utt.volume = 0.9;
        const voices = window.speechSynthesis.getVoices();
        const preferred = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Google') || v.name.includes('Natural'))) || voices.find(v => v.lang.startsWith('en'));
        if (preferred) utt.voice = preferred;
        utt.onstart = () => {
          card.classList.remove('frame-pending');
          card.classList.add('frame-active');
          card.scrollIntoView({ behavior: 'smooth', block: 'start' });
          const idx = _csFrameCards.indexOf(card);
          if (idx >= 0) _csCurrentSlideIndex = idx;
          document.getElementById('audioLabel').textContent = 'Narration Active';
          document.getElementById('audioPauseBtn').textContent = '⏸ Pause';
        };
        window.speechSynthesis.speak(utt);
      }
    });
    csShowAudioBar();
  };
  document.getElementById('outputContainer').appendChild(btn);
}

/** Hide the audio bar only once the scheduled audio queue has finished playing. */
function csHideAudioBarWhenDone() {
  if (!csAudioCtx || csAudioMuted) {
    document.getElementById('audioBar').style.display = 'none';
    cs2SetNarrating(false);
    return;
  }
  const remaining = csNextAudioTime - csAudioCtx.currentTime;
  if (remaining <= 0) {
    document.getElementById('audioBar').style.display = 'none';
    cs2SetNarrating(false);
  } else {
    setTimeout(csHideAudioBarWhenDone, Math.min(remaining * 1000 + 300, 2000));
  }
}

// ─── CS → CS3 Handoff ─────────────────────────────────────────────────────────
let cs3PendingHandoff = null;

function pushToCS3() {
  let telemetry;
  try { telemetry = JSON.parse(document.getElementById('telemetryInput').value); }
  catch { alert('No valid telemetry to push.'); return; }

  const handoff = {
    telemetry,
    routeCoords: _csRouteCoords,
    geCoords:    _csLastGECoords,
    origin:      _csTelemetryOrigin,
    dest:        _csTelemetryDest,
  };
  cs3PendingHandoff = handoff;
  try { localStorage.setItem('cs3-last-handoff', JSON.stringify(handoff)); } catch (e) {}

  switchPhase(3);
  cs3ShowHandoffBanner(handoff);
  cs3PopulateTicket(handoff);
  cs3RenderRouteMap(handoff);
}

function cs3ToggleTicket() {
  document.getElementById('cs3-ticket-card')?.classList.toggle('ll-ticket-collapsed');
}

function cs3PopulateTicket(handoff) {
  const card = document.getElementById('cs3-ticket-card');
  const body = document.getElementById('cs3-ticket-body');
  if (!card || !body) return;

  const t      = handoff.telemetry || {};
  const origin = handoff.origin || t.origin || 'Unknown Origin';
  const dest   = handoff.dest   || t.destination || 'Unknown Destination';
  const sev    = (t.severity || 'UNKNOWN').toUpperCase();
  const sevEmoji = sev.includes('CRITICAL') ? '🔴' : sev.includes('MEDIUM') || sev.includes('AMBER') ? '🟡' : '🟢';
  const services = (t.affected_services || []).join(', ') || '—';

  document.getElementById('cs3-ticket-priority').textContent = sevEmoji;
  document.getElementById('cs3-ticket-title').textContent =
    `${origin} → ${dest} — ${(t.diagnosis_category || 'Circuit Issue').replace(/_/g, ' ')}`;

  const measuredMs = t.expected_latency_ms != null && t.delta_ms != null
    ? (Number(t.expected_latency_ms) + Number(t.delta_ms)).toFixed(1) + ' ms'
    : '—';
  const deltaPct = t.delta_pct != null ? `+${Number(t.delta_pct).toFixed(1)}%` : '';

  body.innerHTML = `
    <div class="ll-ticket-main">
      <div>
        <div class="ll-ticket-section-label">Description</div>
        <div class="ll-ticket-desc">
          <strong>Origin:</strong> Situation Intelligence Brief — Approved for Execution<br/>
          <strong>Issue:</strong> ${(t.diagnosis_category || 'Network issue').replace(/_/g, ' ')}<br/>
          <strong>Action:</strong> ${t.recommended_action || 'Execute circuit reroute'}
        </div>
      </div>
      <div>
        <div class="ll-ticket-section-label">Circuit Details</div>
        <div class="ll-circuit-list">
          <div class="ll-circuit-row"><span class="ll-circuit-label">A-End</span><span class="ll-circuit-value">${origin}</span></div>
          <div class="ll-circuit-row"><span class="ll-circuit-label">Z-End</span><span class="ll-circuit-value">${dest}</span></div>
          ${t.expected_latency_ms != null ? `<div class="ll-circuit-row"><span class="ll-circuit-label">Expected RTT</span><span class="ll-circuit-value">${t.expected_latency_ms} ms</span></div>` : ''}
          ${measuredMs !== '—' ? `<div class="ll-circuit-row"><span class="ll-circuit-label">Measured RTT</span><span class="ll-circuit-value ll-value-bad">${measuredMs} ${deltaPct ? '▲ ' + deltaPct : ''}</span></div>` : ''}
          <div class="ll-circuit-row"><span class="ll-circuit-label">Affected</span><span class="ll-circuit-value" style="font-size:11px">${services}</span></div>
        </div>
      </div>
      <button class="ll-btn-ge" onclick="cs3OpenGE()" style="margin-top:8px">
        🌍 View Route in Google Earth
      </button>
    </div>
    <div class="ll-ticket-sidebar">
      <div class="ll-ts-section">
        <div class="ll-ticket-section-label">Details</div>
        <div class="ll-ts-field"><div class="ll-ts-label">Assignee</div><div class="ll-ts-value ll-ts-urgency">Circuit Stitcher</div></div>
        <div class="ll-ts-field"><div class="ll-ts-label">Severity</div><div class="ll-ts-value ll-ts-highest">${sev}</div></div>
        <div class="ll-ts-field"><div class="ll-ts-label">Status</div><div class="ll-ts-value ll-ts-urgency">Executing</div></div>
        <div class="ll-ts-field"><div class="ll-ts-label">Approved by</div><div class="ll-ts-value">Situation Intelligence Brief</div></div>
      </div>
    </div>
  `;
  card.style.display = '';
  card.classList.remove('ll-ticket-collapsed'); // show expanded — mirrors Phase 1 behaviour
}

function cs3ShowHandoffBanner(handoff) {
  const banner = document.getElementById('cs3HandoffBanner');
  const meta   = document.getElementById('cs3HandoffMeta');
  if (meta && handoff.telemetry) {
    const t = handoff.telemetry;
    meta.textContent = `${t.severity || ''} · ${handoff.origin || t.origin || ''} → ${handoff.dest || t.destination || ''}`;
  }
  if (banner) banner.style.display = 'block';
}

function cs3DismissHandoff() {
  const banner = document.getElementById('cs3HandoffBanner');
  if (banner) banner.style.display = 'none';
}

function cs3OpenGE() {
  const h = cs3PendingHandoff;
  const ge = h?.geCoords;
  const rc = h?.routeCoords;
  if (ge) openGoogleEarth(ge.la, ge.lo, ge.di);
  else if (rc) openGoogleEarth((rc.lat1 + rc.lat2) / 2, (rc.lon1 + rc.lon2) / 2, 2000000);
  else openGoogleEarth(35.0, -117.0, 1800000); // SFO→PHX region fallback

  if (!h) return;
  const t       = h.telemetry || {};
  const origin  = h.origin  || t.origin       || 'Origin';
  const dest    = h.dest    || t.destination  || 'Destination';
  const action  = t.recommended_action || 'Reroute via approved corridor.';
  const cid     = t.circuit_id ? `Circuit ${t.circuit_id} — ` : '';

  // Show task instruction in execution log
  cs3AppendTranscript(`[Google Earth opened] ${cid}${origin} → ${dest}`, 'system');
  cs3AppendTranscript(`TASK: ${action}`, 'system');

  // Send scan trigger — do NOT reveal the expected answer, let the agent observe
  if (cs3Ws && cs3Ws.readyState === WebSocket.OPEN) {
    const brief =
      `[GOOGLE_EARTH_OPENED] Google Earth is now open. Screen share is active.\n` +
      `Circuit on screen: ${origin} → ${dest} (${t.circuit_id || 'N/A'})\n` +
      `Begin VISUAL SCAN PROTOCOL now.\n` +
      `Start with STEP 1: describe the polyline shape you see on screen right now.\n` +
      `Do NOT assume the route is correct or incorrect. Look first, judge second.`;
    cs3Ws.send(JSON.stringify({ type: 'override_alert', text: brief }));
  }
}

function cs3RenderRouteMap(handoff) {
  const panel  = document.getElementById('cs3-route-panel');
  const mapDiv = document.getElementById('cs3-route-map');
  if (!panel || !mapDiv) return;

  const rc     = handoff?.routeCoords;
  const t      = handoff?.telemetry || {};
  const origin = handoff?.origin || t.origin || 'SFO';
  const dest   = handoff?.dest   || t.destination || 'PHX';

  const lat1 = rc?.lat1 ?? t.origin_lat      ?? 37.6213;
  const lon1 = rc?.lon1 ?? t.origin_lon      ?? -122.3790;
  const lat2 = rc?.lat2 ?? t.destination_lat ?? 33.4373;
  const lon2 = rc?.lon2 ?? t.destination_lon ?? -112.0078;

  // Remove any previous static map
  mapDiv.querySelectorAll('img.cs3-static-map').forEach(el => el.remove());

  // ── SIMULATION: Google Earth API (hardcoded) ─────────────────────────────
  // wrong_path.png is a pre-rendered screenshot standing in for a live
  // Google Earth Web Embed, which requires a Maps Platform billing account
  // and the Google Earth API (currently restricted / waitlisted).
  //
  // Production replacement — uncomment once API credentials are provisioned:
  //   const iframe = document.createElement('iframe');
  //   iframe.src = `https://earth.google.com/web/@${(lat1+lat2)/2},${(lon1+lon2)/2},0a,1800000d/embed`;
  //   iframe.allow = 'xr-spatial-tracking';
  //   iframe.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border:0;z-index:2';
  //   mapDiv.appendChild(iframe);
  //
  // The screenshot shows fiber traffic routed over the Sierra Nevada mountains
  // (the "wrong path" — should follow I-10 Southern Corridor via Los Angeles).
  // Opaque paint blocker — sits at z-index:1 directly below the RGBA PNG (z-index:2).
  // PNG transparent pixels composite against THIS element, not the screen-capture stream.
  const blocker = document.createElement('div');
  blocker.className = 'cs3-map-blocker';
  mapDiv.appendChild(blocker);

  const badImg = document.createElement('img');
  badImg.className = 'cs3-static-map';
  badImg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;z-index:2;transition:opacity 0.6s';
  badImg.src = 'wrong_path.png';
  badImg.alt = 'Current wrong route — Sierra Nevada violation';
  mapDiv.appendChild(badImg);

  cs3UpdateRouteStatus('invalid');
}

function cs3UpdateRouteStatus(state) {
  const badge = document.getElementById('cs3-route-status');
  if (!badge) return;
  badge.className = 'cs3-route-status-badge';
  const states = {
    scanning: ['⟳ Scanning…',  'cs3-status-scanning'],
    invalid:  ['⚠ Route Invalid', 'cs3-status-invalid'],
    valid:    ['✓ Route Valid',  'cs3-status-valid'],
  };
  const [text, cls] = states[state] || ['', ''];
  if (!text) { badge.classList.add('hidden'); return; }
  badge.textContent = text;
  badge.classList.add(cls);
  badge.classList.remove('hidden');
}

// ══════════════════════════════════════════════════════════════════════════════
// PHASE 3 — CIRCUIT STITCHER
// ══════════════════════════════════════════════════════════════════════════════

// ─── CS3 State ────────────────────────────────────────────────────────────────
let cs3SessionActive  = false;
let cs3Ws             = null;
let cs3MicStream      = null;
let cs3CaptureCtx     = null;
let cs3WorkletNode    = null;
let cs3ScreenStream   = null;
let cs3ScreenActive   = false;
let cs3FrameInterval   = null;
let cs3AnalyseInterval = null;
let cs3ScanCountdown   = null;  // 1-second tick driving the scan timer badge
let _cs3ScanSecsLeft   = 10;

// Phase 3 audio playback (24 kHz PCM from Gemini)
let cs3PlaybackCtx  = null;
let cs3NextPlayTime = 0;
const cs3ActiveSrcs = [];

function cs3EnsurePlaybackCtx() {
  if (!cs3PlaybackCtx) {
    cs3PlaybackCtx = new AudioContext({ sampleRate: 24000 });
    cs3NextPlayTime = 0;
  }
  if (cs3PlaybackCtx.state === 'suspended') cs3PlaybackCtx.resume();
}

function cs3ScheduleAudio(b64) {
  cs3EnsurePlaybackCtx();
  try {
    const binary = atob(b64);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const int16  = new Int16Array(bytes.buffer);
    const f32    = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768;
    const buf    = cs3PlaybackCtx.createBuffer(1, f32.length, 24000);
    buf.getChannelData(0).set(f32);
    const src    = cs3PlaybackCtx.createBufferSource();
    src.buffer   = buf;
    src.connect(cs3PlaybackCtx.destination);
    const startAt = Math.max(cs3NextPlayTime, cs3PlaybackCtx.currentTime + 0.05);
    src.start(startAt);
    cs3NextPlayTime = startAt + buf.duration;
    cs3ActiveSrcs.push(src);
    src.onended = () => {
      const i = cs3ActiveSrcs.indexOf(src);
      if (i >= 0) cs3ActiveSrcs.splice(i, 1);
      if (cs3ActiveSrcs.length === 0) cs3SetAISpeaking(false);
    };
    cs3SetAISpeaking(true);
  } catch (e) { console.error('cs3ScheduleAudio', e); }
}

function cs3ClearAudioQueue() {
  for (const s of [...cs3ActiveSrcs]) { try { s.stop(); } catch (e) {} }
  cs3ActiveSrcs.length = 0;
  cs3SetAISpeaking(false);
}

function cs3SetAISpeaking(on) {
  document.getElementById('cs3-speaking-indicator')?.classList.toggle('hidden', !on);
  // Show listening indicator only when session active and AI is not speaking
  const listening = cs3SessionActive && !on;
  document.getElementById('cs3-listening-indicator')?.classList.toggle('hidden', !listening);
}

// ─── CS3 Transcript ───────────────────────────────────────────────────────────
let cs3TextAccum = '';

function cs3Timestamp() {
  return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function cs3AppendTranscript(text, type = 'ai') {
  if (text && text.trim()) _dbgLog('p3', text, type === 'error' ? 'error' : type === 'system' ? 'system' : 'info');
  const container = document.getElementById('cs3-transcript');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `ll-transcript-entry ll-entry-${type}`;
  div.innerHTML = `<span class="ll-transcript-time">${cs3Timestamp()}</span><span class="ll-transcript-text"></span>`;
  container.appendChild(div);
  const textEl = div.querySelector('.ll-transcript-text');
  if (type === 'ai') {
    // Typewriter word-by-word reveal synced to speaking
    const words = text.split(/(\s+)/);
    let i = 0;
    const interval = setInterval(() => {
      if (i < words.length) {
        textEl.textContent += words[i++];
      } else {
        clearInterval(interval);
      }
    }, 55);
  } else {
    textEl.textContent = text;
  }
  container.scrollTop = container.scrollHeight;
}

function cs3AppendAction(action) {
  if (action.command === 'CLICK_SAVE') {
    cs3AppendTranscript('Route committed — please review and approve.', 'system');
  } else {
    cs3AppendTranscript('Fixing the route, please wait…', 'system');
    cs3AnimateI10Route();
  }
}

// ─── CS3 Route Verdict Detection ──────────────────────────────────────────────
let _cs3AnimTriggered    = false;
let _cs3RouteWasInvalid  = false;

function cs3CheckReroutePhrase(text) {
  if (_cs3AnimTriggered || !text || !cs3ScreenActive) return;
  const t = text.toLowerCase();
  if (/snapping|re.engag|rerouting|southern corridor|motorway i.10|approved corridor|plotting|committing|new route|route committed/i.test(t)) {
    _cs3AnimTriggered = true;
    cs3AnimateI10Route();
  }
}

// Watches for agent VALID/INVALID verdicts — triggers I-10 suggestion on INVALID
// Only acts while screen share is active (prevents false triggers from system-prompt echoes)
function cs3CheckValidVerdict(text) {
  if (!text || !cs3ScreenActive) return;
  _dbgLog('p3', `Verdict check — screenActive=${cs3ScreenActive} | text="${text.slice(0,80)}"`, 'info');
  if (/ROUTE INVALID|SCAN COMPLETE[^.]*INVALID/i.test(text) && !_cs3AnimTriggered) {
    _dbgLog('p3', 'VERDICT: ROUTE INVALID → triggering I-10 animation', 'warn');
    _cs3AnimTriggered = true;
    _cs3RouteWasInvalid = true;
    cs3UpdateRouteStatus('invalid');
    cs3AppendTranscript('[Route invalid — displaying I-10 Southern Corridor suggestion]', 'system');
    if (geWindowRef && !geWindowRef.closed) { geWindowRef.close(); geWindowRef = null; }
    cs3StopScreenShare();
    setTimeout(cs3AnimateI10Route, 800);
  }
  if (/ROUTE VALID|SCAN COMPLETE[^.]*VALID/i.test(text) && !/INVALID/i.test(text)) {
    _dbgLog('p3', 'VERDICT: ROUTE VALID → resolving ticket and ending session', 'info');
    _cs3ResolveTicket('route confirmed valid by agent');
    cs3AppendTranscript('[Route confirmed valid — ending session in ~5s]', 'system');
    // Tell agent to sign off verbally, then auto-stop
    if (cs3Ws && cs3Ws.readyState === WebSocket.OPEN) {
      cs3Ws.send(JSON.stringify({
        type: 'override_alert',
        text: 'ROUTE CONFIRMED VALID. Say exactly this and nothing else: "Ending session — the route is good." Then stop speaking.',
      }));
    }
    setTimeout(cs3StopSession, 5000);
  }
}

// ─── CS3 I-10 Route Animation ─────────────────────────────────────────────────
// HARDCODED: Approved southern corridor for C2891-W-SFO-PHX only.
// In production, waypoints would be fetched from a network topology API:
//
//   async function _fetchApprovedCorridor(circuitId) {
//     const res = await fetch(`/api/circuits/${circuitId}/approved-corridor`);
//     const data = await res.json();
//     return data.waypoints.map(w => [w.lat, w.lon]);
//     // Expected response shape:
//     // { corridor_name: "I-10 Southern Desert", waypoints: [{ lat, lon, label }] }
//   }
//
// Until the network topology API is available, the SFO→PHX I-10 route is hardcoded:
const _I10_NODES = [
  [37.6213, -122.3790],  // SFO
  [35.28,   -120.66],    // San Luis Obispo (coastal approach)
  [34.42,   -119.70],    // Santa Barbara
  [34.05,   -118.25],    // Los Angeles — I-10 starts here
  [34.06,   -117.65],    // Ontario
  [33.82,   -116.54],    // Palm Springs
  [33.62,   -114.60],    // Blythe (CA/AZ border)
  [32.72,   -114.62],    // Yuma (dip south, avoids elevation band)
  [32.22,   -110.97],    // Tucson
  [33.44,   -112.01],    // PHX
];

function cs3AnimateI10Route() {
  _dbgLog('p3', 'Animating I-10 Southern Corridor route', 'info');
  const mapDiv = document.getElementById('cs3-route-map');
  if (!mapDiv) return;

  // Ensure bad-route map is visible first
  if (!mapDiv.querySelector('img.cs3-static-map') && cs3PendingHandoff) {
    cs3RenderRouteMap(cs3PendingHandoff);
  }

  cs3UpdateRouteStatus('scanning');

  // Fade out bad route image
  const badImg = mapDiv.querySelector('img.cs3-static-map');
  if (badImg) badImg.style.opacity = '0.15';

  // Build I-10 static map: green polyline over all waypoints
  const i10Path = 'color:0x22c55eff|weight:5|' + _I10_NODES.map(n => `${n[0]},${n[1]}`).join('|');
  const url = _staticMap(i10Path, [
    `size:small|color:green|label:S|${_I10_NODES[0][0]},${_I10_NODES[0][1]}`,
    `size:small|color:green|label:D|${_I10_NODES[_I10_NODES.length-1][0]},${_I10_NODES[_I10_NODES.length-1][1]}`,
  ]);

  if (!url) return;

  const newImg = document.createElement('img');
  newImg.className = 'cs3-static-map cs3-static-map-i10';
  newImg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;z-index:3;opacity:0;transition:opacity 1.2s';
  newImg.src = url;
  newImg.onload = () => {
    newImg.style.opacity = '1';
    cs3UpdateRouteStatus('valid');
    cs3AppendTranscript('✓ I-10 Southern Corridor committed — RTT returning to 11.1 ms baseline.', 'system');
    cs3ShowApprovalBar(cs3PendingHandoff);
  };
  mapDiv.appendChild(newImg);
}

// ─── CS3 Route Approval ───────────────────────────────────────────────────────
function cs3ShowApprovalBar(handoff) {
  const panel = document.getElementById('cs3-route-panel');
  if (!panel) return;
  document.getElementById('cs3-approval-bar')?.remove();

  const t          = handoff?.telemetry || {};
  const origin     = (handoff?.origin || t.origin || 'SFO').replace(/ \(.*/, '');
  const dest       = (handoff?.dest   || t.destination || 'PHX').replace(/ \(.*/, '');
  const expectedMs = t.expected_latency_ms ?? 11.1;
  const measuredMs = t.measured_latency_ms || ((+t.expected_latency_ms || 0) + (+t.delta_ms || 0)) || 15.2;

  const bar = document.createElement('div');
  bar.id = 'cs3-approval-bar';
  bar.className = 'cs3-approval-bar';
  bar.innerHTML = `
    <div class="cs3-approval-info">
      <div class="cs3-approval-title">Route Corrected</div>
      <div class="cs3-approval-detail">${origin} → ${dest} via I-10 Southern Corridor</div>
      <div class="cs3-approval-rtt">RTT <span class="cs3-rtt-bad">${measuredMs} ms</span> → <span class="cs3-rtt-good">${expectedMs} ms</span></div>
    </div>
    <div class="cs3-approval-actions">
      <button class="cs3-btn-approve" onclick="cs3ApproveRoute()">✓ Approve &amp; Close Ticket</button>
      <button class="cs3-btn-end-session" onclick="cs3StopSession()">■ End Session</button>
    </div>
  `;
  panel.appendChild(bar);
}

// Shared: mark ticket resolved + close GE window.
// In-memory only — no persistence, resets on page refresh.
function _cs3ResolveTicket(reason) {
  const statusEl = document.querySelector('#cs3-ticket-card .ll-ticket-status');
  if (statusEl) {
    statusEl.textContent = 'Resolved';
    statusEl.style.cssText = 'color:#22c55e;background:rgba(34,197,94,0.1);border-color:rgba(34,197,94,0.3);font-size:10px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;border:1px solid;border-radius:3px;padding:2px 8px;flex-shrink:0';
  }
  cs3UpdateRouteStatus('valid');
  cs3AppendTranscript(`[Ticket resolved — ${reason}]`, 'system');
  _dbgLog('p3', `Ticket resolved: ${reason}`, 'info');
  // Close the Google Earth window that was opened to inspect the route
  if (geWindowRef && !geWindowRef.closed) {
    geWindowRef.close();
    geWindowRef = null;
    _dbgLog('p3', 'Google Earth window closed', 'system');
  }
}

function cs3ApproveRoute() {
  _cs3ResolveTicket('route change approved by operator');
  const bar = document.getElementById('cs3-approval-bar');
  if (bar) {
    bar.innerHTML = `<div class="cs3-approval-done">✓ Route approved and ticket closed. Ending session…</div>`;
  }
  setTimeout(cs3StopSession, 1800);
}

function cs3ClearTranscript() {
  const el = document.getElementById('cs3-transcript');
  if (el) el.innerHTML = '';
  cs3TextAccum = '';
}

// ─── CS3 Status ───────────────────────────────────────────────────────────────
let _cs3Status = { cls: '', label: 'Standby' };

function cs3SetListening(on) {
  document.getElementById('cs3-listening-indicator')?.classList.toggle('hidden', !on);
}

function cs3SetStatus(state) {
  const cls   = (state === 'connected' || state === 'executing') ? 'active' : '';
  const label = { connected: 'Connected', executing: 'Executing', disconnected: 'Disconnected', error: 'Error' }[state] || 'Standby';
  _cs3Status = { cls, label };
  if (activePhase === 3) _applyStatus(cls, label);
}

// ─── CS3 Session ──────────────────────────────────────────────────────────────
function cs3HandleSessionBtn() {
  if (!cs3SessionActive) cs3StartSession(); else cs3StopSession();
}

function cs3HandleScreenBtn() {
  if (!cs3ScreenActive) cs3StartScreenShare(); else cs3StopScreenShare();
}

async function cs3StartSession() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const cs3Key = getApiKey();
  const wsUrl = `${protocol}://${location.host}/cs-ws` + (cs3Key ? `?api_key=${encodeURIComponent(cs3Key)}` : '');

  cs3SessionActive = true;
  _cs3AnimTriggered = false;
  _cs3RouteWasInvalid = false;
  const btn = document.getElementById('cs3-session-btn');
  btn.className = 'll-btn ll-btn-red';
  btn.innerHTML = '&#9632; Stop Session';
  document.getElementById('cs3-screen-btn').classList.remove('hidden');
  cs3SetStatus('connected');
  cs3AppendTranscript('[Session starting…]', 'system');

  cs3Ws = new WebSocket(wsUrl);
  cs3Ws.onopen = async () => {
    _dbgLog('p3', `WS connected → ${wsUrl}`, 'system');
    cs3AppendTranscript('[Connected to Situation Intelligence Brief]', 'system');
    await cs3StartMic();
    cs3StartKeywordDetection();
    cs3SetListening(true);
    // Check GE after agent has had a moment to initialise
    setTimeout(_cs3NotifyGeVisibility, 2000);
  };
  cs3Ws.onclose = () => {
    _dbgLog('p3', 'WS closed', 'system');
    cs3AppendTranscript('[Session closed]', 'system');
    cs3StopSession();
  };
  cs3Ws.onerror = (e) => {
    _dbgLog('p3', `WS error: ${e.message || 'unknown'}`, 'error');
    cs3AppendTranscript('[WebSocket error]', 'error');
  };
  cs3Ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'audio') {
      cs3ScheduleAudio(msg.data);
    } else if (msg.type === 'text') {
      cs3AppendTranscript(msg.content, 'ai');
      cs3CheckReroutePhrase(msg.content);
      cs3CheckValidVerdict(msg.content);
    } else if (msg.type === 'action') {
      cs3AppendAction(msg);
      cs3SetStatus('executing');
    } else if (msg.type === 'interrupted') {
      cs3ClearAudioQueue();
      cs3AppendTranscript('[Interrupted — listening]', 'system');
    } else if (msg.type === 'error') {
      cs3AppendTranscript(`[ERROR: ${msg.message}]`, 'error');
    }
  };
}

function cs3StopSession() {
  cs3SessionActive = false;
  _cs3AnimTriggered = false;
  _cs3RouteWasInvalid = false;
  document.getElementById('cs3-approval-bar')?.remove();
  cs3StopScreenShare();
  cs3StopKeywordDetection();
  if (cs3WorkletNode) { try { cs3WorkletNode.disconnect(); } catch (e) {} cs3WorkletNode = null; }
  if (cs3CaptureCtx)  { cs3CaptureCtx.close().catch(() => {}); cs3CaptureCtx = null; }
  if (cs3MicStream)   { cs3MicStream.getTracks().forEach(t => t.stop()); cs3MicStream = null; }
  if (cs3Ws && cs3Ws.readyState === WebSocket.OPEN) cs3Ws.close();
  cs3Ws = null;
  cs3ClearAudioQueue();
  cs3SetListening(false);
  document.getElementById('cs3-speaking-indicator')?.classList.add('hidden');
  document.getElementById('cs3-mic-badge')?.classList.replace('ll-badge-active-green', 'll-badge-inactive');
  cs3SetStatus('disconnected');
  document.getElementById('cs3-screen-btn').classList.add('hidden');
  const btn = document.getElementById('cs3-session-btn');
  btn.className = 'll-btn ll-btn-green';
  btn.innerHTML = '&#9654; Start Session';
}

// ─── CS3 Mic Capture ──────────────────────────────────────────────────────────
async function cs3StartMic() {
  try {
    cs3MicStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 48000 },
      video: false,
    });
    cs3CaptureCtx = new AudioContext();
    const workletCode = `
class PCMCapture extends AudioWorkletProcessor {
  constructor() { super(); this._buf = []; }
  process(inputs) {
    const ch = inputs[0]?.[0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i += 3) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      this._buf.push(s < 0 ? s * 0x8000 : s * 0x7FFF);
    }
    if (this._buf.length >= 1024) {
      this.port.postMessage(new Int16Array(this._buf.splice(0, 1024)));
    }
    return true;
  }
}
registerProcessor('pcm-capture', PCMCapture);`;
    const blob = new Blob([workletCode], { type: 'application/javascript' });
    const url  = URL.createObjectURL(blob);
    await cs3CaptureCtx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const src = cs3CaptureCtx.createMediaStreamSource(cs3MicStream);
    cs3WorkletNode = new AudioWorkletNode(cs3CaptureCtx, 'pcm-capture');
    cs3WorkletNode.port.onmessage = (e) => {
      if (cs3Ws?.readyState === WebSocket.OPEN) {
        const b64 = btoa(String.fromCharCode(...new Uint8Array(e.data.buffer)));
        cs3Ws.send(JSON.stringify({ type: 'audio', data: b64 }));
      }
    };
    src.connect(cs3WorkletNode);
    document.getElementById('cs3-mic-badge')?.classList.replace('ll-badge-inactive', 'll-badge-active-green');
  } catch (e) {
    cs3AppendTranscript(`[Mic error: ${e.message}]`, 'error');
  }
}

// ─── CS3 Google Earth visibility check ────────────────────────────────────────
// Called after session opens and after screen share starts.
// If Google Earth popup is not open, agent is told it cannot see the map.
function _cs3NotifyGeVisibility() {
  if (!cs3Ws || cs3Ws.readyState !== WebSocket.OPEN) return;
  const geOpen = geWindowRef && !geWindowRef.closed;
  if (geOpen) return;  // all good — nothing to say
  _dbgLog('p3', 'Google Earth not open — notifying agent', 'warn');
  cs3AppendTranscript('[Google Earth not open — agent notified]', 'system');
  cs3Ws.send(JSON.stringify({
    type: 'override_alert',
    text: 'IMPORTANT: Google Earth is not currently open and you cannot see the route map visually. ' +
          'Tell the user: "I cannot see Google Earth right now — please open it for visual route analysis." ' +
          'Then continue with telemetry data only until Google Earth is shared.',
  }));
}

// ─── CS3 Screen Share ─────────────────────────────────────────────────────────
async function cs3StartScreenShare() {
  try {
    cs3ScreenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    cs3ScreenActive = true;
    document.getElementById('cs3-screen-badge')?.classList.replace('ll-badge-inactive', 'll-badge-active-amber');
    const btn = document.getElementById('cs3-screen-btn');
    btn.innerHTML = '&#x1F5A5; Stop Screen';
    _dbgLog('p3', 'Screen share started — 1fps frame interval active', 'system');
    cs3AppendTranscript('[Screen share active — sending frames]', 'system');
    // Show live agent view; hide Leaflet map until it's needed
    const agentView = document.getElementById('cs3-agent-view');
    if (agentView) agentView.style.display = 'block';
    cs3ScreenStream.getVideoTracks()[0].onended = () => cs3StopScreenShare();
    // Re-check GE visibility now that the agent can see frames
    setTimeout(_cs3NotifyGeVisibility, 1500);
    // Send 1 frame per second
    cs3FrameInterval = setInterval(() => cs3SendFrame(), 1000);
    // Scan countdown — ticks every second, resets to 10 when analyse fires
    _cs3ScanSecsLeft = 10;
    cs3ScanCountdown = setInterval(() => {
      _cs3ScanSecsLeft = Math.max(0, _cs3ScanSecsLeft - 1);
      const el = document.getElementById('cs3-scan-timer');
      if (el) el.textContent = ` · scan ${_cs3ScanSecsLeft}s`;
    }, 1000);
    // Every 10 seconds — enough time for the agent to complete a full 4-step scan
    cs3AnalyseInterval = setInterval(() => {
      _cs3ScanSecsLeft = 10;  // reset countdown
      if (cs3Ws?.readyState === WebSocket.OPEN) {
        cs3UpdateRouteStatus('scanning');
        cs3Ws.send(JSON.stringify({
          type: 'override_alert',
          text: 'FRAME SCAN. Look at the current frame only. STEP 1: describe the polyline shape in one sentence — where does it start, which direction does it travel, does it curve north or south, where does it end. Do not judge yet. Describe only what you see.',
        }));
      }
    }, 10000);
  } catch (e) {
    cs3AppendTranscript(`[Screen error: ${e.message}]`, 'error');
  }
}

function cs3StopScreenShare() {
  _dbgLog('p3', 'Screen share stopped — last frame frozen', 'system');
  clearInterval(cs3FrameInterval);   cs3FrameInterval = null;
  clearInterval(cs3AnalyseInterval); cs3AnalyseInterval = null;
  clearInterval(cs3ScanCountdown);   cs3ScanCountdown = null;
  const timerEl = document.getElementById('cs3-scan-timer');
  if (timerEl) timerEl.textContent = '';
  if (cs3ScreenStream) { cs3ScreenStream.getTracks().forEach(t => t.stop()); cs3ScreenStream = null; }
  cs3ScreenActive = false;
  // Keep last captured frame visible — it shows what the agent just scanned
  document.getElementById('cs3-screen-badge')?.classList.replace('ll-badge-active-amber', 'll-badge-inactive');
  const btn = document.getElementById('cs3-screen-btn');
  if (btn) { btn.innerHTML = '&#x1F5A5; Share Screen'; }
}

function cs3SendFrame() {
  if (!cs3ScreenStream || !cs3Ws || cs3Ws.readyState !== WebSocket.OPEN) return;
  const track = cs3ScreenStream.getVideoTracks()[0];
  if (!track) return;
  const cap = new ImageCapture(track);
  cap.grabFrame().then(bmp => {
    const canvas = document.createElement('canvas');
    const scale  = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
    canvas.width  = Math.floor(bmp.width  * scale);
    canvas.height = Math.floor(bmp.height * scale);
    canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
    cs3Ws.send(JSON.stringify({ type: 'frame', data: dataUrl.split(',')[1] }));
    // Mirror latest frame into the agent-view panel
    const agentView = document.getElementById('cs3-agent-view');
    if (agentView) agentView.src = dataUrl;
  }).catch(() => {});
}

// ─── CS3 Override Alert ───────────────────────────────────────────────────────
function cs3FireOverride() {
  if (!cs3Ws || cs3Ws.readyState !== WebSocket.OPEN) return;
  const text = "[OVERRIDE_ALERT] Human engineer is drawing a route through prohibitive mountainous terrain! Invoke the absolute co-pilot barge-in rule immediately.";
  cs3Ws.send(JSON.stringify({ type: 'override_alert', text }));
  cs3AppendTranscript('[Override alert sent]', 'system');
}

// ─── CS3 Voice Stop Detection ─────────────────────────────────────────────────
let cs3SpeechRecog = null;

function cs3StartKeywordDetection() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  try {
    cs3SpeechRecog = new SR();
    cs3SpeechRecog.continuous = true;
    cs3SpeechRecog.interimResults = false;
    cs3SpeechRecog.lang = 'en-US';
    cs3SpeechRecog.onresult = (e) => {
      if (!cs3SessionActive) return;
      const transcript = e.results[e.results.length - 1][0].transcript.toLowerCase().trim();
      if (/\b(stop|end|finish|done|exit|close)\b/.test(transcript)) {
        cs3AppendTranscript('[Voice command detected — ending session]', 'system');
        setTimeout(cs3StopSession, 300);
      }
    };
    cs3SpeechRecog.onerror = () => {};
    cs3SpeechRecog.onend = () => {
      // Restart if session is still active (it auto-stops after silence)
      if (cs3SessionActive && cs3SpeechRecog) {
        try { cs3SpeechRecog.start(); } catch (e) {}
      }
    };
    cs3SpeechRecog.start();
  } catch (e) {}
}

function cs3StopKeywordDetection() {
  if (cs3SpeechRecog) {
    try { cs3SpeechRecog.stop(); } catch (e) {}
    cs3SpeechRecog = null;
  }
}

// ─── Init ──────────────────────────────────────────────────────────────────────
csOutputContainer = document.getElementById('outputContainer');

// Auto-scroll: follows new content unless the user manually scrolled up
let _csAutoScroll = true;
csOutputContainer.addEventListener('scroll', () => {
  const distFromBottom = csOutputContainer.scrollHeight - csOutputContainer.scrollTop - csOutputContainer.clientHeight;
  _csAutoScroll = distFromBottom < 80;
});

function csScrollToBottom() {
  if (!_csAutoScroll) return;
  requestAnimationFrame(() => {
    csOutputContainer.scrollTop = csOutputContainer.scrollHeight;
  });
}

// Pre-load voices
if (window.speechSynthesis) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.addEventListener('voiceschanged', () => window.speechSynthesis.getVoices());
}
