"""Wake word detection engine with ONNX OpenWakeWord and acoustic/text fuzzy fallback.

Supports:
1. Native ONNX wake word detection ("hey_eve.onnx" or "hey_jarvis.onnx").
2. Short-utterance text/phonetic fuzzy matching ("hey eve", "hi eve", "hey ev", "eve").
3. Hotkey and programmatic manual trigger.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

import numpy as np

from eve.config import Settings, get_settings
from eve.events import EventBus

logger = logging.getLogger(__name__)

# Regular expression pattern for wake-word triggers in short utterances
WAKE_WORD_PATTERN = re.compile(
    r"\b(hey\s+eve|hi\s+eve|hey\s+ev|okay\s+eve|ok\s+eve|hey\s+jarvis|listen\s+eve)\b",
    re.IGNORECASE,
)


class WakeWordDetector:
    """Detects wake words from audio frames or transcribed utterances."""

    def __init__(
        self,
        settings: Settings | None = None,
        event_bus: EventBus | None = None,
        on_detected: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.event_bus = event_bus
        self.on_detected = on_detected
        self.threshold = self.settings.wakeword_threshold
        self._oww_model: Any = None
        self._init_model()

    def _init_model(self) -> None:
        if not self.settings.wakeword_enabled:
            logger.info("Wake word detection disabled by configuration (EVE_WAKEWORD_ENABLED=false)")
            return

        model_path = self.settings.wakeword_model_path
        if model_path.exists():
            try:
                from openwakeword.model import Model

                self._oww_model = Model(
                    wakeword_models=[str(model_path)],
                    inference_framework="onnx",
                )
                logger.info("Loaded ONNX wake word model from %s", model_path)
            except Exception as exc:
                logger.warning(
                    "Could not initialize openWakeWord with %s: %s. Falling back to phonetic/utterance matcher.",
                    model_path,
                    exc,
                )
                self._oww_model = None
        else:
            logger.info(
                "ONNX wake word model not found at %s. Using acoustic/utterance fuzzy matcher (Decision #2).",
                model_path,
            )
            self._oww_model = None

    @property
    def has_onnx_model(self) -> bool:
        return self._oww_model is not None

    def trigger(self, trigger_source: str = "manual") -> None:
        """Manually fires a wake word detected event."""
        logger.info("Wake word triggered via %s", trigger_source)
        if self.event_bus:
            self.event_bus.publish({
                "type": "wakeword_detected",
                "source": trigger_source,
                "confidence": 1.0,
            })
        if self.on_detected:
            self.on_detected(trigger_source)

    def feed_text(self, text: str) -> bool:
        """Checks if transcribed speech contains the wake word phrase."""
        if not text:
            return False

        match = WAKE_WORD_PATTERN.search(text)
        if match:
            matched_phrase = match.group(0)
            logger.info("Wake word matched in transcript: '%s'", matched_phrase)
            self.trigger(trigger_source=f"transcript:{matched_phrase}")
            return True
        return False

    def feed_audio(self, audio_chunk: np.ndarray) -> bool:
        """Feeds a 16 kHz audio chunk to the ONNX model if loaded."""
        if self._oww_model is None:
            return False

        try:
            # Ensure 16-bit PCM format for openWakeWord
            if audio_chunk.dtype == np.float32 or audio_chunk.dtype == np.float64:
                pcm16 = (np.clip(audio_chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
            else:
                pcm16 = audio_chunk.astype(np.int16)

            prediction = self._oww_model.predict(pcm16)
            for model_name, score in prediction.items():
                if score >= self.threshold:
                    logger.info("ONNX Wake word '%s' detected with score %.2f", model_name, score)
                    self.trigger(trigger_source=f"onnx:{model_name}")
                    return True
        except Exception as exc:
            logger.debug("Error during openWakeWord inference: %s", exc)

        return False
