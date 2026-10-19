"""faster-whisper wrapper tuned for live, code-switched (Bisaya/Tagalog/English) lectures."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from eve.stt.cuda_dlls import register_cuda_dlls

log = logging.getLogger(__name__)

# Phrases Whisper is known to hallucinate on noise/music; only dropped when they are the
# *entire* output of a short utterance, so real speech containing them is kept.
_HALLUCINATIONS = {
    "thank you for watching", "thanks for watching", "please subscribe",
    "subscribe to my channel", "thank you", "you", "bye",
}


@dataclass(slots=True)
class TranscribedText:
    text: str
    language: str | None
    avg_logprob: float | None


class SpeechToText(Protocol):
    device: str

    def transcribe(self, samples: np.ndarray) -> TranscribedText | None: ...


class WhisperTranscriber:
    def __init__(
        self,
        model_name: str,
        models_dir: Path,
        *,
        device: str = "auto",
        language: str | None = None,
        initial_prompt: str | None = None,
        beam_size: int = 1,
    ) -> None:
        from faster_whisper import WhisperModel  # heavy import, keep lazy

        self.language = language
        self.initial_prompt = initial_prompt
        self.beam_size = beam_size
        download_root = str(models_dir / "whisper")

        attempts: list[tuple[str, str]] = []
        if device in ("auto", "cuda"):
            register_cuda_dlls()
            attempts.append(("cuda", "int8_float16"))
        if device in ("auto", "cpu"):
            attempts.append(("cpu", "int8"))

        last_error: Exception | None = None
        for dev, compute in attempts:
            try:
                model = WhisperModel(model_name, device=dev, compute_type=compute, download_root=download_root)
                # Force kernel/DLL loading now so a missing cuDNN fails here, not mid-lecture.
                model.transcribe(np.zeros(16_000, dtype=np.float32), language="en", beam_size=1)
                self._model = model
                self.device = dev
                self.compute_type = compute
                log.info("Whisper %s loaded on %s (%s)", model_name, dev, compute)
                return
            except Exception as exc:  # noqa: BLE001 - fall back to next device
                last_error = exc
                log.warning("Whisper load failed on %s (%s): %s", dev, compute, exc)
        raise RuntimeError(f"Could not load Whisper model {model_name!r}") from last_error

    def transcribe(self, samples: np.ndarray) -> TranscribedText | None:
        segments, info = self._model.transcribe(
            samples.astype(np.float32, copy=False),
            language=self.language,
            multilingual=self.language is None,  # per-segment language detection for code-switching
            beam_size=self.beam_size,
            vad_filter=False,  # Silero already segmented upstream
            condition_on_previous_text=False,  # stops hallucination loops across utterances
            initial_prompt=self.initial_prompt,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
        )
        kept: list[str] = []
        logprobs: list[float] = []
        for seg in segments:
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                continue
            if seg.compression_ratio > 2.4:  # repetitive garbage
                continue
            text = seg.text.strip()
            if text:
                kept.append(text)
                logprobs.append(seg.avg_logprob)
        text = " ".join(kept).strip()
        if not text:
            return None
        duration = len(samples) / 16_000
        if duration < 3.0 and text.lower().strip(" .!?,") in _HALLUCINATIONS:
            return None
        return TranscribedText(
            text=text,
            language=getattr(info, "language", None),
            avg_logprob=float(np.mean(logprobs)) if logprobs else None,
        )
