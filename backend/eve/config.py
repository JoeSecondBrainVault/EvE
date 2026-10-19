"""Runtime configuration loaded from environment variables (prefix ``EVE_``) and ``.env``.

Secrets are never given defaults here. Phase 2+ reads ``GEMINI_API_KEY`` straight from
the environment so it never lands in a settings dump or log line.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Bias Whisper toward code-switched Visayan/Tagalog/English classroom speech.
# Whisper treats the initial prompt as "previous text", so a realistic mixed
# sentence nudges it to keep Bisaya/Tagalog words instead of translating them.
DEFAULT_CODE_SWITCH_PROMPT = (
    "Okay class, karon atong i-discuss ang lesson. Unsa man ang inyong pangutana? "
    "Sige, let's continue. Ang deadline sa assignment kay sa Friday, ha. "
    "Intindi ninyo? Okay, tapos na ta sa quiz."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVE_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8765
    allowed_origins: list[str] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ]

    # --- storage ---
    data_dir: Path = PROJECT_ROOT / "data"
    models_dir: Path = PROJECT_ROOT / "models"

    # --- speech-to-text ---
    whisper_model: str = "large-v3-turbo"
    whisper_device: Literal["auto", "cuda", "cpu"] = "auto"
    language: str | None = None
    vocabulary: str = ""
    code_switch_prompt: str = DEFAULT_CODE_SWITCH_PROMPT

    # --- capture ---
    capture_loopback: bool = True
    capture_mic: bool = True

    # --- voice activity detection ---
    vad_threshold: float = 0.5
    vad_min_silence_s: float = 0.6
    vad_max_utterance_s: float = 15.0
    vad_min_utterance_s: float = 0.4

    # --- language models & intelligence ---
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fast_model: str = "llama-3.1-8b-instant"
    ollama_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    cloud_transcribe: bool = True

    # --- obsidian integration (Phase 2) ---
    vault_path: Path = Path(r"C:\Users\Legion\Documents\Obsidian Vault")
    lecture_folder: str = "13 - Lectures"

    # --- RAG & embeddings (Phase 3) ---
    embedding_model: str = "text-embedding-004"
    ollama_embedding_model: str = "nomic-embed-text"

    # --- Google Classroom & Calendar (Phase 4) ---
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_client_secrets_file: Path | None = None
    google_calendar_name: str = "E.V.E."
    google_sync_interval_m: int = 30

    # --- Voice Assistant & TTS (Phase 5) ---
    wakeword_enabled: bool = True
    wakeword_model: str = "hey_jarvis"
    wakeword_threshold: float = 0.5
    tts_enabled: bool = True
    tts_engine: Literal["edge-tts", "kokoro"] = "edge-tts"
    edge_tts_voice: str = "en-PH-RosaNeural"
    tts_voice: str = "af_sarah"
    tts_speed: float = 1.0

    # --- Live Copilot (Phase 5) ---
    copilot_enabled: bool = True
    copilot_window_s: int = 180

    # --- Retention & Hardening (Phase 6) ---
    retention_days: int = 30
    max_upload_size_bytes: int = 20 * 1024 * 1024  # 20 MB max
    rate_limit_chat_rpm: int = 60
    tray_enabled: bool = False

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        # The API exposes live microphone transcripts; never bind it to a LAN interface.
        if value not in _LOOPBACK_HOSTS:
            raise ValueError(f"EVE_HOST must be a loopback address, got {value!r}")
        return value

    @field_validator("language", mode="before")
    @classmethod
    def _empty_language_is_auto(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def db_path(self) -> Path:
        return self.data_dir / "eve.db"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def initial_prompt(self) -> str:
        vocab = self.vocabulary.strip()
        return f"{self.code_switch_prompt} {vocab}".strip() if vocab else self.code_switch_prompt

    @property
    def resolved_gemini_api_key(self) -> str | None:
        import os

        return self.gemini_api_key or os.environ.get("GEMINI_API_KEY")

    @property
    def resolved_groq_api_key(self) -> str | None:
        import os

        return self.groq_api_key or os.environ.get("GROQ_API_KEY")

    @property
    def lectures_dir(self) -> Path:
        return self.vault_path / self.lecture_folder

    @property
    def tts_model_path(self) -> Path:
        return self.models_dir / "kokoro-v0_19.onnx"

    @property
    def tts_voices_path(self) -> Path:
        return self.models_dir / "voices.json"

    @property
    def wakeword_model_path(self) -> Path:
        return self.models_dir / f"{self.wakeword_model}.onnx"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.models_dir, self.recordings_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
