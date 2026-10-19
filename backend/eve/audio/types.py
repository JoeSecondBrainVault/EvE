"""Shared audio types and DSP helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000  # Whisper + Silero native rate

SOURCE_THEM = "them"  # system audio (WASAPI loopback): professor, classmates, meeting
SOURCE_ME = "me"      # default microphone: you


@dataclass(slots=True)
class AudioFrame:
    """Mono float32 samples at 16 kHz. ``t_end`` = seconds since session start when received."""

    source: str
    samples: np.ndarray
    t_end: float

    @property
    def t_start(self) -> float:
        return self.t_end - len(self.samples) / SAMPLE_RATE


@dataclass(slots=True)
class Utterance:
    source: str
    t0: float
    t1: float
    samples: np.ndarray


def int16_bytes_to_mono_float(data: bytes, channels: int) -> np.ndarray:
    """Interleaved int16 PCM -> mono float32 in [-1, 1]."""
    pcm = np.frombuffer(data, dtype=np.int16)
    if channels > 1:
        usable = len(pcm) - (len(pcm) % channels)
        pcm = pcm[:usable].reshape(-1, channels).mean(axis=1)
    return (pcm.astype(np.float32) / 32768.0).astype(np.float32, copy=False)


def float_to_int16(samples: np.ndarray) -> np.ndarray:
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
