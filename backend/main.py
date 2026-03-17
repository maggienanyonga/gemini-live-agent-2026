# ══════════════════════════════════════════════════════════════════════════════
# Clarity Studio — Backend API
# ══════════════════════════════════════════════════════════════════════════════
#
# API SIMULATIONS & KEY REQUIREMENTS
# -----------------------------------
# Several features are simulated due to API access limitations.
# Real implementations are commented inline. Summary:
#
#  Feature                   Status           Requires
#  ─────────────────────────────────────────────────────────────────────────
#  Gemini text generation     ✅ LIVE          GEMINI_API_KEY (env or header)
#  Gemini Live audio (Phase1) ✅ LIVE          GEMINI_API_KEY — v1beta
#  Gemini Live audio (Phase3) ✅ LIVE          GEMINI_API_KEY — v1alpha
#  Google Search grounding    ✅ LIVE          GEMINI_API_KEY (paid tier)
#  Code execution (Skills)    ✅ LIVE          GEMINI_API_KEY
#  Image generation           ✅ LIVE (chain)  GEMINI_API_KEY — tries 6 models
#  Vertex AI RAG Engine       🔶 SIMULATED     GCP project + Vertex AI billing
#                                              See HARDCODED_SLA_DOC + comment
#                                              in stream_gemini() below
#  Google Earth Web Embed     🔶 SIMULATED     Maps Platform billing account
#                                              + Earth API access (waitlisted)
#                                              See frontend/app.js cs3RenderRouteMap
#  Network topology API       🔶 SIMULATED     Internal NOC system integration
#                                              See _I10_NODES + build_cs_system_prompt
#                                              comment in prompt.py
#  Google Maps Static API     🔶 KEY REQUIRED  Maps Platform — Static Maps API
#                                              Silently disabled when key absent
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import base64
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import AsyncIterator, Literal, Optional

from fastapi import FastAPI, Header, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

from google import genai
from google.genai import types

from prompt import SYSTEM_PROMPT, build_user_prompt, LL_SYSTEM_PROMPT, LL_MODEL, CS_MODEL, CS_SYSTEM_PROMPT, parse_cs_action_tags

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clarity-studio")

app = FastAPI(title="Clarity Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_AUDIENCES = {"CFO", "CTO", "CEO", "VP Engineering", "VP Finance"}

VALID_GROUNDING = {"NONE", "RAG", "GOOGLE_SEARCH", "SKILLS", "EXTRA_CONTEXT"}

# ── RAG Context Document ──────────────────────────────────────────────────────
# Simulates Google RAG / Vertex AI Grounding with Search.
# In production this would be retrieved from a Vertex AI Search corpus or
# a Google Cloud Storage bucket via Vertex AI RAG Engine.
# Source: Aegius Benchmarking — Agreed Sample SLAs
HARDCODED_SLA_DOC = """
SOURCE: Aegius Benchmarking — Agreed Sample SLAs
GROUNDING: Vertex AI RAG Engine simulation (Google Search + enterprise corpus)
PAPERS: Beyond the Topology Illusion | Evaluating AI Agent Governance | AI for Network Resilience Assessment

PURPOSE
To ensure the Aegius Framework delivers mission-critical value to both technical and executive
stakeholders, the following SLAs are established. These metrics are grounded in Inference
Economics Research and planetary-scale network standards (ION-2030).

CORE FRAMEWORK SLAs

System Availability    99.999%   "Five 9s" uptime for Aegius Control Plane and sensing nodes.
                                  Protects infrastructure costing $14,056/min during downtime.

Interaction Velocity   < 500 ms  Real-time audio/vision response delay from Gemini 2.5 Flash nodes.
                                  Prevents the 30% engagement erosion caused by high-latency AI.

Audit Velocity         < 10 min  Time to complete a planetary-scale circuit audit (Sense→Translate→Stitch).
                                  99% reduction from the traditional 2–3 week manual audit cycle.

Diagnostic Precision   Sub-ms    Alignment with ION-2030 for deterministic latency detection.
                                  Resolves the "Topology Illusion" — RTT values match physical reality.

Financial Safeguard    < $4,800  Maximum allowable exposure to the Recompute Tax per GPU cluster/mo.
                                  Directly protects the Inference Moat and operational profitability.

Briefing Delivery      < 10 sec  Time to generate an interleaved multimodal storyboard for executives.
                                  Collapses the "Communication Void" between NOC and boardroom.

GROUNDING INTEGRATION
Vertex AI Grounding integrates Google Search to provide real-time competitive analysis of global
token pricing and regional SLA benchmarks across 111 countries.

SLA REFERENCE GROUNDING
Availability: Enterprise-class resilience requirements — average downtime cost $2M/hour.
Latency:      Sparkco (2025) — threshold of human-computer interaction perception and engagement impact.
Inference:    Tensormesh (2025) — inference now accounts for the vast majority of total AI compute costs.
""".strip()

# ── Gemini client singletons ─────────────────────────────────────────────────
# One per process lifetime; two separate clients because the Live API
# requires api_version="v1beta" while the SSE generation API uses the default.

_gemini_client: genai.Client | None = None
_ll_client: genai.Client | None = None
_ll_config: types.LiveConnectConfig | None = None

# Runtime prompt overrides — edited from the UI, cleared on process restart
_prompt_overrides: dict[str, str] = {}

# Connected PyAutoGUI execution clients (local runner processes)
_exec_clients: set[WebSocket] = set()


class AgentAction(BaseModel):
    """Structured action returned by the Circuit Stitcher VLM loop."""
    narration: str
    command: Literal["CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "DRAG", "TYPE", "KEY", "SCROLL", "WAIT", "DONE"]
    x: Optional[int] = None
    y: Optional[int] = None
    from_x: Optional[int] = None
    from_y: Optional[int] = None
    to_x: Optional[int] = None
    to_y: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    amount: Optional[int] = None


def _cs_generate_action(api_key: str | None, frame_bytes: bytes, system_prompt: str) -> dict | None:
    """Run one VLM step: analyze screen frame, return structured AgentAction dict."""
    effective_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    logger.info("CS using api_key=%s... (source=%s)",
                effective_key[:12] if effective_key else "NONE",
                "query_param" if api_key else "env_var")
    client = _client_for_key(api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=AgentAction,
        temperature=0.1,
        max_output_tokens=512,
    )
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg"),
            types.Part.from_text(text="Analyze the screen and take the next action toward the mission goal."),
        ],
        config=config,
    )
    if not resp.candidates:
        return None
    return json.loads(resp.text) if resp.text else None


def get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def get_ll_client() -> genai.Client:
    global _ll_client
    if _ll_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _ll_client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=api_key,
        )
    return _ll_client


def get_ll_config() -> types.LiveConnectConfig:
    global _ll_config
    if _ll_config is None:
        _ll_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            media_resolution="MEDIA_RESOLUTION_MEDIUM",
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
                )
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                    silence_duration_ms=600,
                    prefix_padding_ms=20,
                )
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=104857,
                sliding_window=types.SlidingWindow(target_tokens=52428),
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=_prompt_overrides.get("phase1", LL_SYSTEM_PROMPT))],
                role="user",
            ),
        )
    return _ll_config


_cs_config: types.LiveConnectConfig | None = None


def get_cs_config() -> types.LiveConnectConfig:
    global _cs_config
    if _cs_config is None:
        _cs_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            media_resolution="MEDIA_RESOLUTION_MEDIUM",
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=_prompt_overrides.get("phase3", CS_SYSTEM_PROMPT))],
                role="user",
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=104857,
                sliding_window=types.SlidingWindow(target_tokens=52428),
            ),
        )
    return _cs_config


class ViewportImage(BaseModel):
    """Optional Google Earth viewport screenshot, base64-encoded."""
    mime_type: str = "image/jpeg"
    data: str  # raw base64, no data-URL prefix

    @field_validator("data")
    @classmethod
    def must_be_valid_base64(cls, v: str) -> str:
        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("viewport_image.data must be valid base64")
        return v


class BriefingRequest(BaseModel):
    telemetry: dict
    audience_type: str = "CTO"
    viewport_image: ViewportImage | None = None
    grounding_type: str = "NONE"   # NONE | RAG | GOOGLE_SEARCH | SKILLS | EXTRA_CONTEXT
    extra_context: str | None = None  # max 8000 chars — validated below

    @field_validator("extra_context")
    @classmethod
    def extra_context_length(cls, v: str | None) -> str | None:
        if v and len(v) > 8000:
            raise ValueError("extra_context must be ≤ 8000 characters")
        return v

    @field_validator("telemetry")
    @classmethod
    def telemetry_not_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("telemetry payload must not be empty")
        return v

    @field_validator("audience_type")
    @classmethod
    def audience_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_AUDIENCES:
            raise ValueError(
                f"audience_type must be one of: {', '.join(sorted(VALID_AUDIENCES))}"
            )
        return v

    @field_validator("grounding_type")
    @classmethod
    def grounding_must_be_valid(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in VALID_GROUNDING:
            raise ValueError(f"grounding_type must be one of: {', '.join(sorted(VALID_GROUNDING))}")
        return v


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/prompts")
async def get_prompts():
    """Return all active system prompts (overrides take precedence)."""
    return {
        "phase1": {"name": "Latency Lens Live", "model": LL_MODEL,
                   "prompt": _prompt_overrides.get("phase1", LL_SYSTEM_PROMPT),
                   "modified": "phase1" in _prompt_overrides},
        "phase2": {"name": "Situation Intelligence Brief", "model": "gemini-2.5-flash",
                   "prompt": _prompt_overrides.get("phase2", SYSTEM_PROMPT),
                   "modified": "phase2" in _prompt_overrides},
        "phase3": {"name": "Circuit Stitcher", "model": CS_MODEL,
                   "prompt": _prompt_overrides.get("phase3", CS_SYSTEM_PROMPT),
                   "modified": "phase3" in _prompt_overrides},
    }


@app.put("/prompts/{phase}")
async def update_prompt(phase: str, payload: dict):
    """Save an edited system prompt. Invalidates Live session config caches."""
    global _ll_config, _cs_config
    if phase not in ("phase1", "phase2", "phase3"):
        return {"ok": False, "error": "unknown phase"}
    text = payload.get("prompt", "").strip()
    if not text:
        return {"ok": False, "error": "empty prompt"}
    _prompt_overrides[phase] = text
    # Invalidate cached Live configs so next session uses the new prompt
    if phase == "phase1":
        _ll_config = None
    elif phase == "phase3":
        _cs_config = None
    logger.info("Prompt updated for %s (%d chars)", phase, len(text))
    return {"ok": True, "phase": phase, "length": len(text)}


@app.delete("/prompts/{phase}")
async def reset_prompt(phase: str):
    """Revert a phase prompt back to the default from prompt.py."""
    global _ll_config, _cs_config
    _prompt_overrides.pop(phase, None)
    if phase == "phase1":
        _ll_config = None
    elif phase == "phase3":
        _cs_config = None
    return {"ok": True, "phase": phase}


def _build_contents(
    user_message: str,
    viewport_image: ViewportImage | None,
) -> list | str:
    """Build Gemini contents — multimodal when a viewport image is supplied."""
    if viewport_image is None:
        return user_message

    return [
        types.Part.from_bytes(
            data=base64.b64decode(viewport_image.data),
            mime_type=viewport_image.mime_type,
        ),
        types.Part.from_text(text=user_message),
    ]


def _client_for_key(api_key: str | None) -> genai.Client:
    """Return a Gemini client — per-request key takes priority over env var."""
    if api_key:
        return genai.Client(api_key=api_key)
    return get_gemini_client()


def _live_client_for_key(api_key: str | None) -> genai.Client:
    """v1beta — for Latency Lens (native audio preview model)."""
    if api_key:
        return genai.Client(http_options={"api_version": "v1beta"}, api_key=api_key)
    return get_ll_client()


def _cs_live_client_for_key(api_key: str | None) -> genai.Client:
    """v1alpha — for Circuit Stitcher (gemini-2.0-flash-live-001, multimodal)."""
    key = api_key or os.environ.get("GEMINI_API_KEY")
    return genai.Client(http_options={"api_version": "v1alpha"}, api_key=key)


async def stream_gemini(
    telemetry: dict,
    audience_type: str,
    viewport_image: ViewportImage | None,
    api_key: str | None = None,
    grounding_type: str = "NONE",
    extra_context: str | None = None,
) -> AsyncIterator[str]:
    """Stream SSE events from Gemini 2.5 Flash (text + native audio)."""
    client = _client_for_key(api_key)
    has_viewport = viewport_image is not None
    user_message = build_user_prompt(telemetry, audience_type, has_viewport=has_viewport)
    contents = _build_contents(user_message, viewport_image)

    # ── Grounding configuration ───────────────────────────────────────────────
    tools: list = []
    system_extra = ""

    if grounding_type == "RAG":
        # ── SIMULATION: Vertex AI RAG Engine ─────────────────────────────────
        # In production this block would be replaced by a Vertex AI RAG call:
        #
        #   from vertexai.preview.rag import RagCorpora, RagRetrieval
        #   from vertexai import init as vertex_init
        #   import vertexai.preview.generative_models as vertex_models
        #
        #   vertex_init(project="your-gcp-project", location="us-central1")
        #
        #   # Step 1 — Retrieve relevant chunks from the corpus
        #   retrieval = RagRetrieval(
        #       source=RagCorpora(rag_corpus="projects/.../ragCorpora/aegius-sla-corpus"),
        #       similarity_top_k=5,
        #   )
        #   rag_tool = vertex_models.Tool.from_retrieval(retrieval)
        #
        #   # Step 2 — Use retrieved chunks as grounding via VertexAI GenerateContent
        #   vertex_model = vertex_models.GenerativeModel(
        #       model_name="gemini-2.5-flash",
        #       tools=[rag_tool],
        #       system_instruction=SYSTEM_PROMPT,
        #   )
        #   response = vertex_model.generate_content(contents, ...)
        #   # grounding_metadata = response.candidates[0].grounding_metadata
        #   # grounding_metadata.retrieval_queries → search queries issued
        #   # grounding_metadata.grounding_chunks  → source document chunks used
        #
        # SIMULATION: inject the corpus document directly into the system prompt.
        # Functionally equivalent — Gemini reasons over the same text that the
        # RAG retriever would have returned as top-k chunks.
        system_extra = (
            "\n\n--- VERTEX AI RAG CONTEXT (Aegius Benchmarking Corpus · simulated retrieval) ---\n"
            + HARDCODED_SLA_DOC
            + "\n--- END RAG CONTEXT ---"
        )
        logger.info("RAG: injecting Aegius Benchmarking SLA corpus (Vertex AI RAG simulation)")

    elif grounding_type == "GOOGLE_SEARCH":
        # Gemini built-in Google Search grounding — real production behaviour
        # (Vertex AI equivalent: vertex_models.Tool.from_google_search_retrieval(...))
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    elif grounding_type == "SKILLS":
        # Gemini code execution tool — model can write + run Python to analyse telemetry
        # (Vertex AI equivalent: vertex_models.Tool.from_code_execution(...))
        tools.append(types.Tool(code_execution=types.ToolCodeExecution()))

    elif grounding_type == "EXTRA_CONTEXT" and extra_context:
        system_extra = (
            "\n\n--- EXTRA CONTEXT (treat as supplementary reference) ---\n"
            + extra_context.strip()
            + "\n--- END EXTRA CONTEXT ---"
        )

    config = types.GenerateContentConfig(
        system_instruction=_prompt_overrides.get("phase2", SYSTEM_PROMPT) + system_extra,
        temperature=0.7,
        max_output_tokens=16384,
        response_modalities=["TEXT"],
        tools=tools if tools else None,
    )

    try:
        yield f"data: {json.dumps({'type': 'start', 'message': 'Situation Intelligence Brief initializing...'})}\n\n"
        if grounding_type != "NONE":
            grounding_labels = {
                "RAG": "Aegius Benchmarking SLAs · Vertex AI RAG (simulated)",
                "GOOGLE_SEARCH": "Google Search",
                "SKILLS": "Skills · Code Execution",
                "EXTRA_CONTEXT": "Extra Context",
            }
            yield f"data: {json.dumps({'type': 'grounding', 'mode': grounding_type, 'label': grounding_labels.get(grounding_type, grounding_type)})}\n\n"
        await asyncio.sleep(0)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def producer():
            try:
                for chunk in client.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=config,
                ):
                    if not chunk.candidates:
                        continue
                    content = chunk.candidates[0].content
                    if not content or not content.parts:
                        continue
                    for part in content.parts:
                        if part.text:
                            asyncio.run_coroutine_threadsafe(
                                queue.put(("text", part.text)), loop
                            )
                        elif (
                            part.inline_data
                            and part.inline_data.mime_type
                            and part.inline_data.mime_type.startswith("audio/")
                        ):
                            audio_b64 = base64.b64encode(part.inline_data.data).decode()
                            asyncio.run_coroutine_threadsafe(
                                queue.put(("audio", (audio_b64, part.inline_data.mime_type))),
                                loop,
                            )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    queue.put(("error", str(e))), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(
                    queue.put(("done", None)), loop
                )

        thread = threading.Thread(target=producer, daemon=True)
        thread.start()

        while True:
            kind, value = await queue.get()
            if kind == "done":
                break
            elif kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': value})}\n\n"
                break
            elif kind == "audio":
                audio_b64, mime_type = value
                yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64, 'mime_type': mime_type})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'chunk', 'text': value})}\n\n"
            await asyncio.sleep(0)

        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


class ImageGenRequest(BaseModel):
    prompt: str
    api_key: str | None = None


@app.get("/list-models")
async def list_models(api_key: str | None = None):
    """Debug: list all models available with the configured API key."""
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=key)
    try:
        models = [m.name for m in client.models.list()]
        image_models = [m for m in models if any(k in m.lower() for k in ("image", "imagen", "flash", "vision"))]
        return {"all_count": len(models), "image_related": image_models, "all": models}
    except Exception as e:
        return {"error": str(e)}


@app.post("/generate-image")
async def generate_image(request: ImageGenRequest):
    """Generate a slide illustration using Gemini image generation.
    Try models in order: gemini-2.5-flash-preview-04-17 → imagen-3.0-generate-002.
    """
    api_key = request.api_key or os.environ.get("GEMINI_API_KEY", "")
    errors = []

    # 1. Gemini image-generation models via v1 — no response_modalities needed,
    #    model returns IMAGE parts natively; v1beta 404s on these model names.
    client_v1 = genai.Client(http_options={"api_version": "v1"}, api_key=api_key)
    for model_name in (
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.0-flash-exp",
    ):
        try:
            resp = client_v1.models.generate_content(
                model=model_name,
                contents=request.prompt,
            )
            for part in resp.candidates[0].content.parts:
                if part.inline_data is not None:
                    img_b64 = base64.b64encode(part.inline_data.data).decode()
                    logger.info(f"Image generated via {model_name}")
                    return {"image": img_b64, "mime_type": part.inline_data.mime_type}
            errors.append(f"{model_name}: no image part in response")
            logger.warning(f"{model_name}: no image part in response")
        except Exception as e:
            errors.append(f"{model_name}: {e}")
            logger.warning(f"{model_name} failed: {e}")

    # 2. Imagen via v1beta (predict endpoint, not generateContent)
    client_beta = genai.Client(http_options={"api_version": "v1beta"}, api_key=api_key)
    for img_model in ("imagen-3.0-generate-002", "imagen-3.0-generate-001"):
        try:
            resp = client_beta.models.generate_images(
                model=img_model,
                prompt=request.prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                ),
            )
            img_bytes = resp.generated_images[0].image.image_bytes
            logger.info(f"Image generated via {img_model}")
            return {"image": base64.b64encode(img_bytes).decode(), "mime_type": "image/jpeg"}
        except Exception as e:
            errors.append(f"{img_model}: {e}")
            logger.warning(f"{img_model} failed: {e}")

    detail = " | ".join(errors)
    logger.error(f"All image models failed: {detail}")
    return Response(content=detail, status_code=502)


@app.post("/generate-briefing")
async def generate_briefing(request: BriefingRequest, x_api_key: str | None = Header(None)):
    return StreamingResponse(
        stream_gemini(
            request.telemetry,
            request.audience_type,
            request.viewport_image,
            api_key=x_api_key,
            grounding_type=request.grounding_type,
            extra_context=request.extra_context,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Latency Lens handoff ──────────────────────────────────────────────────────
# In-memory store: only one pending payload at a time (last wins).
_pending_handoff: dict | None = None
_handoff_seq: int = 0

_LL_SEVERITY_MAP = {
    "green":  "LOW",
    "amber":  "MEDIUM",
    "yellow": "MEDIUM",
    "red":    "CRITICAL",
}


def _normalize_ll_payload(raw: dict) -> dict:
    """Map Latency Lens audit log fields to Clarity Studio telemetry schema."""
    sev_key = str(raw.get("severity", "")).lower().strip()
    severity = _LL_SEVERITY_MAP.get(sev_key, sev_key.upper() or "UNKNOWN")

    return {
        "severity":           severity,
        "expected_latency_ms": raw.get("expected_latency_ms", 0),
        "delta_ms":            raw.get("delta_ms", 0),
        "diagnosis_category":  raw.get("diagnosis_category", "UNKNOWN"),
        "recommended_action":  raw.get("recommended_action", ""),
        "origin":              raw.get("origin", "Unknown Origin"),
        "destination":         raw.get("destination", "Unknown Destination"),
        "affected_services":   raw.get("affected_services", []),
        "timestamp":           raw.get("timestamp")
                               or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Pass through delta_pct for display; Clarity Studio prompt ignores unknown fields
        "delta_pct":           raw.get("delta_pct"),
    }


@app.post("/handoff")
async def receive_handoff(payload: dict):
    """Webhook called by Latency Lens when the operator clicks 'Push to Situation Intelligence Brief'."""
    global _pending_handoff, _handoff_seq
    if not payload:
        return Response(status_code=400, content="empty payload")
    _pending_handoff = _normalize_ll_payload(payload)
    _handoff_seq += 1
    logger.info("Handoff received from Latency Lens (seq=%d): %s", _handoff_seq, _pending_handoff)
    return {"status": "received", "seq": _handoff_seq}


@app.get("/handoff/pending")
async def get_pending_handoff(since: int = 0):
    """Poll endpoint for Clarity Studio frontend.

    Returns 204 (no content) when nothing new has arrived since `since`.
    Returns 200 + JSON when a newer payload exists.
    """
    if _pending_handoff is None or _handoff_seq <= since:
        return Response(status_code=204)
    return {"seq": _handoff_seq, "payload": _pending_handoff}


# ── Latency Lens Live — WebSocket endpoint ───────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Live bidirectional session for Latency Lens (Gemini Live API)."""
    api_key = websocket.query_params.get("api_key") or None
    await websocket.accept()
    try:
        async with _live_client_for_key(api_key).aio.live.connect(
            model=LL_MODEL, config=get_ll_config()
        ) as session:

            async def browser_to_gemini():
                try:
                    while True:
                        msg = await websocket.receive_json()
                        msg_type = msg.get("type")
                        data = msg.get("data")
                        if not data:
                            continue
                        if msg_type == "audio":
                            await session.send_realtime_input(
                                audio={"mime_type": "audio/pcm;rate=16000", "data": data}
                            )
                        elif msg_type == "video":
                            await session.send_realtime_input(
                                video={"mime_type": "image/jpeg", "data": data}
                            )
                except WebSocketDisconnect:
                    pass

            async def gemini_to_browser():
                try:
                    while True:
                        turn = session.receive()
                        async for response in turn:
                            if (
                                hasattr(response, "server_content")
                                and response.server_content
                                and getattr(response.server_content, "interrupted", False)
                            ):
                                await websocket.send_json({"type": "interrupted"})
                            if response.data:
                                await websocket.send_json(
                                    {
                                        "type": "audio",
                                        "data": base64.b64encode(response.data).decode(),
                                    }
                                )
                            if response.text:
                                await websocket.send_json(
                                    {"type": "text", "data": response.text}
                                )
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.error("gemini→browser error: %s", e, exc_info=True)
                    try:
                        await websocket.send_json({"type": "error", "message": str(e)})
                    except Exception:
                        pass
                    raise

            t1 = asyncio.create_task(browser_to_gemini())
            t2 = asyncio.create_task(gemini_to_browser())
            try:
                await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in [t1, t2]:
                    if not task.done():
                        task.cancel()
                for task in [t1, t2]:
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket session error: %s", e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass



# ── Circuit Stitcher WebSocket ────────────────────────────────────────────────

@app.websocket("/cs-ws")
async def cs_websocket_endpoint(websocket: WebSocket):
    """Circuit Stitcher — VLM loop: stores screen frames, calls generate_content on each scan
    trigger, returns structured AgentAction JSON to browser and exec clients. No Gemini Live
    session — guaranteed structured output every call."""
    api_key = websocket.query_params.get("api_key") or None
    await websocket.accept()

    latest_frame_b64: str | None = None
    # maxsize=1 drops duplicate scan triggers while a generate_content call is in flight
    scan_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    cs_prompt = _prompt_overrides.get("phase3", CS_SYSTEM_PROMPT)

    async def browser_to_gemini():
        nonlocal latest_frame_b64
        try:
            while True:
                msg = await websocket.receive_json()
                msg_type = msg.get("type")
                if msg_type == "frame":
                    data = msg.get("data")
                    if data:
                        latest_frame_b64 = data
                elif msg_type == "override_alert":
                    logger.info("CS scan trigger: %s", msg.get("text", "")[:80])
                    if not scan_queue.full():
                        await scan_queue.put(msg.get("text", ""))
                # audio / other message types silently ignored (no Live session)
        except WebSocketDisconnect:
            pass

    async def agent_loop():
        while True:
            await scan_queue.get()
            if latest_frame_b64 is None:
                try:
                    await websocket.send_json({"type": "text", "content": "Waiting for screen frame…"})
                except Exception:
                    break
                continue
            try:
                frame_bytes = base64.b64decode(latest_frame_b64)
                action = await asyncio.to_thread(
                    _cs_generate_action, api_key, frame_bytes, cs_prompt
                )
                if action is None:
                    await websocket.send_json({"type": "text", "content": "[Agent error — retrying next frame]"})
                    continue

                narration = action.get("narration", "")
                if narration:
                    await websocket.send_json({"type": "text", "content": narration})

                command = action.get("command", "WAIT")
                logger.info("CS action: cmd=%s x=%s y=%s narration=%s",
                            command, action.get("x"), action.get("y"), narration[:60])

                if command == "DONE":
                    await websocket.send_json({"type": "action", "command": "CLICK_SAVE"})
                elif command != "WAIT":
                    action_msg = {"type": "action", **action}
                    await websocket.send_json(action_msg)
                    dead: set[WebSocket] = set()
                    for exc in list(_exec_clients):
                        try:
                            await exc.send_json(action_msg)
                        except Exception:
                            dead.add(exc)
                    _exec_clients.difference_update(dead)

            except Exception as e:
                logger.error("CS agent loop error: %s", e, exc_info=True)
                try:
                    await websocket.send_json({"type": "text", "content": f"[Agent error: {e}]"})
                except Exception:
                    break

    t1 = asyncio.create_task(browser_to_gemini())
    t2 = asyncio.create_task(agent_loop())
    try:
        await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in [t1, t2]:
            if not task.done():
                task.cancel()
        for task in [t1, t2]:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


# ── Execution client WebSocket ────────────────────────────────────────────────

@app.websocket("/exec-ws")
async def exec_websocket(websocket: WebSocket):
    """Local PyAutoGUI execution client. Receives action events and sends acks."""
    await websocket.accept()
    _exec_clients.add(websocket)
    logger.info("Execution client connected. Total: %d", len(_exec_clients))
    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "ack":
                logger.info("Action ack: command=%s status=%s error=%s",
                            msg.get("command"), msg.get("status"), msg.get("error") or "")
    except WebSocketDisconnect:
        pass
    finally:
        _exec_clients.discard(websocket)
        logger.info("Execution client disconnected. Remaining: %d", len(_exec_clients))


@app.get("/exec-status")
async def exec_status():
    """Returns how many execution clients are currently connected."""
    return {"connected": len(_exec_clients)}


# ── Serve frontend static files ───────────────────────────────────────────────
_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
_frontend = os.path.abspath(_frontend)
if os.path.isdir(_frontend):
    @app.get("/")
    async def index():
        return FileResponse(os.path.join(_frontend, "index.html"))

    app.mount("/", StaticFiles(directory=_frontend), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
