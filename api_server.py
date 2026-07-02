"""
Automotive Service AI Agent — FastAPI REST API Server
=====================================================
Run: uvicorn api_server:app --reload --port 8000

Voice layer powered by SoundHound AI (Houndify STT + NLU + TTS).
Set env vars:
  SOUNDHOUND_API_KEY    — from https://www.soundhound.com/soundhound-ai-platform/
  SOUNDHOUND_CLIENT_ID  — from your Houndify developer dashboard
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from main import AutomotiveServiceOrchestrator, ServiceType

# Read SoundHound credentials from environment (never hard-code)
SOUNDHOUND_API_KEY   = os.getenv("SOUNDHOUND_API_KEY",   "SOUNDHOUND_API_KEY_PLACEHOLDER")
SOUNDHOUND_CLIENT_ID = os.getenv("SOUNDHOUND_CLIENT_ID", "SOUNDHOUND_CLIENT_ID_PLACEHOLDER")

app = FastAPI(
    title="AutoCare Pro AI Agent API",
    description=(
        "Multi-framework AI agent: CrewAI + AutoGen + Semantic Kernel + "
        "SoundHound AI Voice (Houndify STT/NLU/TTS)"
    ),
    version="2.0.0"
)

# CORS_ORIGINS should be a comma-separated allow-list in production
# (e.g. "https://app.autocarepro.com"). Defaults to "*" for local development.
_cors_origins = os.getenv("CORS_ORIGINS", "*")
_allow_origins = ["*"] if _cors_origins.strip() == "*" else [o.strip() for o in _cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware, allow_origins=_allow_origins, allow_methods=["*"], allow_headers=["*"]
)

orchestrator = AutomotiveServiceOrchestrator(
    soundhound_api_key=SOUNDHOUND_API_KEY,
    soundhound_client_id=SOUNDHOUND_CLIENT_ID,
)


# ─── Request Models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None

class BookingRequest(BaseModel):
    customer_id: str
    service_type: str
    preferred_date: str
    preferred_time: Optional[str] = None

class PhoneCallRequest(BaseModel):
    caller_phone: str
    conversation: list[str]

class SoundHoundTranscribeRequest(BaseModel):
    """
    Simulate a single STT transcription turn via SoundHound AI.
    In production, replace `audio_text` with a base64-encoded PCM audio chunk
    and stream it to the Houndify endpoint.
    """
    audio_text: str          # pre-transcribed text (simulation) or raw utterance
    session_id: Optional[str] = None

class SoundHoundNLURequest(BaseModel):
    """Run Houndify NLU intent extraction on raw text."""
    transcript: str

class SoundHoundTTSRequest(BaseModel):
    """Synthesise spoken audio via SoundHound TTS."""
    text: str
    voice: str = "ARIA-Neural-EN"

class NewCustomerRequest(BaseModel):
    name: str
    phone: str
    email: str
    vehicle_make: str
    vehicle_model: str
    vehicle_year: int


# ─── Core Endpoints ───────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "AutoCare Pro AI Agent",
        "version": "2.0.0",
        "agents": [
            "ARIA (CrewAI)",
            "APEX (AutoGen)",
            "NEXUS (Semantic Kernel)",
            "VOICE (SoundHound AI — Houndify STT/NLU/TTS)",
        ],
        "soundhound": {
            "stt_engine":  "SoundHound Houndify ASR",
            "nlu_engine":  "Houndify NLU v3",
            "tts_engine":  "SoundHound Neural TTS",
            "edge_module": "SoundHound Edge (on-device wake-word)",
            "docs":        "https://www.soundhound.com/soundhound-ai-platform/",
        },
        "status": "operational",
    }

@app.post("/chat")
async def chat(req: ChatRequest):
    """Chat via CrewAI receptionist — auto-triggers booking & CRM."""
    return orchestrator.handle_chat_interaction(req.message, req.phone)

@app.post("/book")
async def book(req: BookingRequest):
    """Direct booking via AutoGen agent."""
    try:
        service = ServiceType(req.service_type)
    except ValueError:
        raise HTTPException(400, f"Valid services: {[s.value for s in ServiceType]}")
    result = orchestrator.booking_agent.orchestrate_booking(
        req.customer_id, service, req.preferred_date, req.preferred_time
    )
    if not result["success"]:
        raise HTTPException(404, result.get("error"))
    return result

@app.post("/call")
async def call(req: PhoneCallRequest):
    """
    Simulate a complete phone call through the SoundHound AI voice pipeline.

    Each item in `conversation` is treated as a caller utterance and routed
    through: SoundHound STT → Houndify NLU → ARIA (CrewAI) → SoundHound TTS.
    """
    return orchestrator.handle_phone_call(req.caller_phone, req.conversation)

@app.get("/crm/{customer_id}")
async def crm_profile(customer_id: str):
    """Semantic Kernel CRM intelligence pipeline."""
    result = orchestrator.crm_agent.run_customer_pipeline(customer_id)
    if not result["success"]:
        raise HTTPException(404, result.get("error"))
    return result

@app.post("/customers")
async def create_customer(req: NewCustomerRequest):
    c = orchestrator.crm.create_customer(
        req.name, req.phone, req.email,
        req.vehicle_make, req.vehicle_model, req.vehicle_year
    )
    return {"success": True, "customer_id": c.id}

@app.get("/customers")
async def list_customers():
    return orchestrator.get_crm_dashboard()["customers"]

@app.get("/appointments")
async def list_appointments():
    return orchestrator.get_crm_dashboard()["appointments"]

@app.get("/dashboard")
async def dashboard():
    return orchestrator.get_crm_dashboard()

@app.get("/slots/{date}")
async def slots(date: str):
    available = orchestrator.crm.get_available_slots(date)
    return {"date": date, "available_slots": available}


# ─── SoundHound AI Endpoints ──────────────────────────────────────────────────

@app.post("/soundhound/transcribe")
async def soundhound_transcribe(req: SoundHoundTranscribeRequest):
    """
    SoundHound STT — transcribe a caller utterance.

    Production: stream raw PCM audio chunks to this endpoint and receive
    partial + final transcripts with per-word confidence scores.

    Simulation: pass `audio_text` (pre-transcribed string) to get realistic
    SoundHound STT metadata including confidence, language detection, and
    word-level timestamps.
    """
    stt_engine = orchestrator.voice_handler.stt_engine
    # Start a session if none provided
    if not req.session_id:
        stt_engine.start_session()
    result = stt_engine.transcribe(req.audio_text)
    return {"soundhound_stt": result}

@app.post("/soundhound/nlu")
async def soundhound_nlu(req: SoundHoundNLURequest):
    """
    Houndify NLU — extract intent and named entities from transcript text.

    Returns primary intent, all matched intents, and entity slots
    (service_type, time_expression, urgency).
    """
    stt_engine = orchestrator.voice_handler.stt_engine
    result = stt_engine.extract_intent(req.transcript)
    return {"houndify_nlu": result}

@app.post("/soundhound/tts")
async def soundhound_tts(req: SoundHoundTTSRequest):
    """
    SoundHound TTS — synthesise text into spoken audio.

    Returns a signed audio URL (mp3), duration estimate, and the
    SSML-cleaned spoken text. In production, the audio URL streams
    directly back to the telephony bridge.
    """
    stt_engine = orchestrator.voice_handler.stt_engine
    result = stt_engine.synthesise_speech(req.text, voice=req.voice)
    return {"soundhound_tts": result}

@app.get("/soundhound/wake-word")
async def soundhound_wake_word(audio_snippet: str = ""):
    """
    SoundHound Edge wake-word detector — checks for 'Hey AutoCare'.

    On-device, no network round-trip required (~5 ms latency).
    Pass ?audio_snippet=hey+autocare to simulate a trigger.
    """
    stt_engine = orchestrator.voice_handler.stt_engine
    result = stt_engine.detect_wake_word(audio_snippet)
    return {"soundhound_edge": result}

@app.get("/soundhound/status")
async def soundhound_status():
    """Return SoundHound AI engine configuration and capabilities."""
    engine = orchestrator.voice_handler.stt_engine
    return {
        "engine":              "SoundHound AI / Houndify",
        "api_key_configured":  engine.api_key != "SOUNDHOUND_API_KEY_PLACEHOLDER",
        "client_id_configured": engine.client_id != "SOUNDHOUND_CLIENT_ID_PLACEHOLDER",
        "supported_languages": engine.SUPPORTED_LANGUAGES,
        "domain_vocab_count":  len(engine.DOMAIN_VOCAB),
        "active_session":      engine.session_id,
        "streaming_active":    engine.is_streaming,
        "capabilities": [
            "Streaming STT (<200ms latency)",
            "On-device wake-word detection (SoundHound Edge)",
            "Automotive domain ASR vocabulary",
            "Multi-language: EN, HI, TE, TA",
            "Per-word confidence scores",
            "Houndify NLU intent + entity extraction",
            "Neural TTS (SSML support)",
            "Speaker diarization",
        ],
    }
