"""Local Text-To-Speech (TTS) engine using Kokoro-ONNX.

Generates high-quality 24 kHz speech locally on CPU without requiring external API calls.
Provides graceful fallbacks if model weights are not yet downloaded into `models/`.
"""

from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Any

import numpy as np

from eve.config import Settings, get_settings

logger = logging.getLogger(__name__)


def pcm_to_wav_bytes(samples: np.ndarray, sample_rate: int = 24000) -> bytes:
    """Encodes float32 or int16 numpy audio samples into standard WAV bytes."""
    if samples.dtype == np.float32 or samples.dtype == np.float64:
        # Clip to [-1.0, 1.0] and convert to 16-bit PCM
        clipped = np.clip(samples, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
    elif samples.dtype == np.int16:
        pcm16 = samples
    else:
        pcm16 = samples.astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return buffer.getvalue()


class TTSEngine:
    """Kokoro-ONNX Text-To-Speech engine with audio playback and fallback synthesis."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._kokoro: Any = None
        self._model_path = self.settings.tts_model_path
        self._voices_path = self.settings.tts_voices_path
        self._lock = threading.Lock()
        self._init_kokoro()

    def _init_kokoro(self) -> None:
        if not self.settings.tts_enabled:
            logger.info("TTS is disabled by configuration (EVE_TTS_ENABLED=false)")
            return

        if self._model_path.exists() and self._voices_path.exists():
            try:
                from kokoro_onnx import Kokoro

                self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))
                logger.info(
                    "Kokoro-ONNX TTS engine initialized successfully from %s",
                    self._model_path,
                )
            except Exception as exc:
                logger.warning("Failed to initialize Kokoro-ONNX: %s. Using fallback synthesis.", exc)
                self._kokoro = None
        else:
            logger.info(
                "Kokoro model files not found at %s or %s. Using fallback synthetic audio until weights are placed.",
                self._model_path,
                self._voices_path,
            )
            self._kokoro = None

    @property
    def is_available(self) -> bool:
        """Returns True if Kokoro weights are loaded, False if running on fallback."""
        return self._kokoro is not None

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        speed: float | None = None,
    ) -> tuple[np.ndarray, int]:
        """Synthesizes input text to audio samples.
        
        Returns:
            (samples_float32, sample_rate)
        """
        text = text.strip()
        if not text:
            return np.zeros(2400, dtype=np.float32), 24000

        selected_voice = voice or self.settings.tts_voice
        selected_speed = speed or self.settings.tts_speed

        if self._kokoro is not None:
            with self._lock:
                try:
                    samples, sample_rate = self._kokoro.create(
                        text,
                        voice=selected_voice,
                        speed=selected_speed,
                        lang="en-us",
                    )
                    return samples.astype(np.float32), int(sample_rate)
                except Exception as exc:
                    logger.error("Kokoro synthesis error: %s. Falling back to synthetic tone.", exc)

        # Fallback synthesis: produce a clean gentle harmonic chime/pulse
        sample_rate = 24000
        duration = min(max(len(text) * 0.05, 0.5), 3.0)  # ~50ms per character
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)
        # 440 Hz fundamental + 880 Hz overtone with exponential decay envelope
        envelope = np.exp(-3.0 * t / duration).astype(np.float32)
        carrier = (0.2 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
        fallback_samples = (carrier * envelope).astype(np.float32)
        return fallback_samples, sample_rate

    def synthesize_wav_bytes(
        self,
        text: str,
        voice: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        """Synthesizes text and formats it directly as standard WAV byte content."""
        samples, rate = self.synthesize(text, voice=voice, speed=speed)
        return pcm_to_wav_bytes(samples, rate)

    def play(
        self,
        samples: np.ndarray,
        sample_rate: int = 24000,
        blocking: bool = False,
    ) -> None:
        """Plays the audio samples through the system output device using sounddevice."""
        try:
            import sounddevice as sd

            sd.play(samples, samplerate=sample_rate)
            if blocking:
                sd.wait()
        except Exception as exc:
            logger.debug("Playback via sounddevice unavailable: %s", exc)

    def speak(
        self,
        text: str,
        voice: str | None = None,
        blocking: bool = False,
    ) -> tuple[np.ndarray, int]:
        """Synthesizes text and plays it out through the speaker."""
        samples, rate = self.synthesize(text, voice=voice)
        self.play(samples, rate, blocking=blocking)
        return samples, rate
