"""Automated tests for Phase 5: Voice Assistant, TTS, Wake Word, and Live Copilot."""

from __future__ import annotations

import io
import wave
from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession

from eve.config import Settings
from eve.llm.router import LLMRouter
from eve.main import Components, create_app
from eve.models import Task
from eve.pipelines.copilot import CopilotItem, LiveCopilot
from eve.voice.assistant import AssistantAction, VoiceAssistant
from eve.voice.tts import TTSEngine
from eve.voice.wakeword import WakeWordDetector


# --- Test TTS Engine ---
def test_tts_engine_fallback_synthesis(tmp_path):
    settings = Settings(models_dir=tmp_path / "models", tts_enabled=True)
    engine = TTSEngine(settings)

    assert not engine.is_available  # Model weights not on disk yet; running fallback
    samples, sample_rate = engine.synthesize("Hello class, welcome to IT 101.")
    assert isinstance(samples, np.ndarray)
    assert sample_rate == 24000
    assert len(samples) > 0
    assert samples.dtype == np.float32

    # Verify WAV byte serialization
    wav_bytes = engine.synthesize_wav_bytes("Short test message")
    assert len(wav_bytes) > 44  # Has valid RIFF/WAVE header
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2  # 16-bit
        assert wf.getframerate() == 24000


# --- Test Wake Word Detector ---
def test_wakeword_detector_text_matching(tmp_path):
    detector = WakeWordDetector(Settings(models_dir=tmp_path / "models"))
    triggered_sources = []
    detector.on_detected = lambda src: triggered_sources.append(src)

    # Positive matches
    assert detector.feed_text("Hey Eve, what are my upcoming assignments?")
    assert len(triggered_sources) == 1
    assert "hey eve" in triggered_sources[0].lower()

    assert detector.feed_text("Hi Eve can you start recording?")
    assert len(triggered_sources) == 2

    assert detector.feed_text("Hey Jarvis, summarize the lecture")
    assert len(triggered_sources) == 3

    # Negative matches
    assert not detector.feed_text("Class please open your textbooks to chapter 3")
    assert not detector.feed_text("Everything is clear for today")
    assert len(triggered_sources) == 3


# --- Mock LLM Router for Assistant & Copilot ---
class FakeAssistantRouter(LLMRouter):
    def __init__(self, settings: Settings, action: AssistantAction | None = None, copilot_item: CopilotItem | None = None):
        super().__init__(settings)
        self.preset_action = action
        self.preset_copilot = copilot_item

    def generate_structured(self, prompt: str, *, system_prompt: str, schema: type[Any]) -> tuple[Any, str]:
        if schema == AssistantAction and self.preset_action:
            return (self.preset_action, "fake_llm")
        if schema == CopilotItem and self.preset_copilot:
            return (self.preset_copilot, "fake_llm")
        # Default fallback
        if schema == AssistantAction:
            return (
                AssistantAction(
                    tool="general_answer",
                    arguments={},
                    spoken_response="I'm here to help, Joe!",
                ),
                "fake_llm",
            )
        if schema == CopilotItem:
            return (
                CopilotItem(
                    topic="Database Normalization",
                    talking_points=["1NF eliminates duplicate columns.", "2NF removes partial functional dependencies."],
                    context_summary="Professor asked about normalization forms.",
                ),
                "fake_llm",
            )
        raise ValueError(f"Unhandled schema: {schema}")


# --- Test Voice Assistant Tool Calling ---
def test_voice_assistant_tool_dispatching(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models")
    settings.ensure_dirs()
    from eve.db import make_engine

    db_engine = make_engine(tmp_path / "data" / "eve.db")

    # 1. Test add_task tool
    action = AssistantAction(
        tool="add_task",
        arguments={"title": "Submit Lab 4", "due_date": "2026-10-25T23:59:00", "course": "IT 202"},
        spoken_response="Added task: Submit Lab 4 due October 25.",
    )
    router = FakeAssistantRouter(settings, action=action)
    assistant = VoiceAssistant(db_engine, router, settings)

    resp = assistant.process_command("Eve add task Submit Lab 4 due October 25 for IT 202", synthesize_audio=True)
    assert resp.tool == "add_task"
    assert resp.tool_output["status"] == "created"
    assert resp.audio_base64 is not None

    with DBSession(db_engine) as db:
        tasks = db.exec(Task.__table__.select()).all()
        assert len(tasks) == 1

    # 2. Test list_deadlines tool
    action2 = AssistantAction(
        tool="list_deadlines",
        arguments={"limit": 5},
        spoken_response="Checking deadlines...",
    )
    router2 = FakeAssistantRouter(settings, action=action2)
    assistant2 = VoiceAssistant(db_engine, router2, settings)

    resp2 = assistant2.process_command("What are my deadlines?", synthesize_audio=False)
    assert resp2.tool == "list_deadlines"
    assert len(resp2.tool_output["tasks"]) == 1
    assert "Submit Lab 4" in resp2.response_text

    # 3. Test start_session consent gating
    action3 = AssistantAction(
        tool="start_session",
        arguments={"title": "Math Lecture"},
        spoken_response="Starting session...",
    )
    router3 = FakeAssistantRouter(settings, action=action3)
    assistant3 = VoiceAssistant(db_engine, router3, settings)
    resp3 = assistant3.process_command("Start recording Math Lecture", synthesize_audio=False)
    assert resp3.tool_output["status"] == "consent_required"

    action4 = AssistantAction(
        tool="start_session",
        arguments={"title": "Math Lecture", "consent_confirmed": True},
        spoken_response="Starting session...",
    )
    router4 = FakeAssistantRouter(settings, action=action4)
    assistant4 = VoiceAssistant(db_engine, router4, settings)
    resp4 = assistant4.process_command("Start recording Math Lecture with consent", synthesize_audio=False)
    assert resp4.tool_output["status"] == "simulated_started"


# --- Test Live Copilot Rolling Window ---
def test_live_copilot_rolling_window(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", copilot_window_s=60)
    settings.ensure_dirs()
    from eve.db import make_engine

    db_engine = make_engine(tmp_path / "data" / "eve.db")
    router = FakeAssistantRouter(settings)
    copilot = LiveCopilot(db_engine, router, settings)

    # Add segments: t0=0, t1=10
    copilot.add_segment("them", "Welcome everyone to computer networks.", 0.0, 10.0)
    copilot.add_segment("them", "Can anyone tell me what the OSI model does?", 15.0, 25.0)

    assert copilot.should_trigger("Can anyone tell me what the OSI model does?")
    window_text = copilot.get_window_text()
    assert "computer networks" in window_text
    assert "OSI model" in window_text

    # Generate suggestion
    suggestion = copilot.generate_suggestion()
    assert suggestion is not None
    assert len(suggestion.talking_points) >= 1

    # Test eviction: segment at t=100s should evict t=10s segment (since 100 - 10 = 90 > 60)
    copilot.add_segment("them", "Now let's move on to the transport layer.", 80.0, 100.0)
    assert "computer networks" not in copilot.get_window_text()
    assert "transport layer" in copilot.get_window_text()


# --- Test Phase 5 API Endpoints ---
def test_phase5_api_endpoints(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        vault_path=tmp_path / "vault",
    )
    settings.ensure_dirs()

    comps = Components(
        load_stt=lambda s: None,
        capture_factory=lambda s: None,
        vad_factory=lambda: None,
        list_devices=lambda: [],
        router_factory=lambda s: FakeAssistantRouter(s),
    )

    app = create_app(settings, comps)

    with TestClient(app) as client:
        token = (settings.data_dir / "api_token").read_text(encoding="ascii").strip()
        headers = {"Authorization": f"Bearer {token}", "Origin": "http://127.0.0.1:3000"}

        # 1. Voice status
        r = client.get("/api/voice/status", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "wakeword_enabled" in data
        assert "tts_enabled" in data
        assert "copilot_enabled" in data


        # 2. Voice interact
        r2 = client.post(
            "/api/voice/interact",
            json={"input": "Hello Eve, how are you?", "synthesize_audio": True},
            headers=headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert "tool" in data2
        assert "response_text" in data2
        assert data2["audio_base64"] is not None

        # 3. Voice speak (WAV audio stream)
        r3 = client.post(
            "/api/voice/speak",
            json={"text": "This is a synthesized test message."},
            headers=headers,
        )
        assert r3.status_code == 200
        assert r3.headers["content-type"] == "audio/wav"
        assert len(r3.content) > 44

        # 4. Wake word trigger
        r4 = client.post("/api/voice/wakeword/trigger", headers=headers)
        assert r4.status_code == 200
        assert r4.json()["status"] == "ok"

        # 5. Copilot suggest & recent
        r5 = client.post(
            "/api/copilot/suggest",
            json={"hint": "Explain binary search trees"},
            headers=headers,
        )
        assert r5.status_code == 200
        assert r5.json()["status"] == "ok"

        r6 = client.get("/api/copilot/recent", headers=headers)
        assert r6.status_code == 200
        assert "suggestion" in r6.json()
