"""Time-aligned WAV recorder.

WASAPI loopback delivers *no callbacks* while nothing is playing, so simply appending
frames would squash silences and break the link between transcript timestamps and
audio. The recorder pads with zeros up to each frame's real start time, so second N in
the file is always second N of the session (needed for click-to-play citations and the
Phase 2 Gemini re-transcription).
"""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np

from eve.audio.types import SAMPLE_RATE, AudioFrame, float_to_int16

_MAX_GAP_S = 6 * 60 * 60  # guard against clock bugs writing gigabytes of zeros


class AlignedWavRecorder:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._wav = wave.open(str(path), "wb")  # noqa: SIM115 (closed in close())
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(SAMPLE_RATE)
        self._written = 0
        self._lock = threading.Lock()

    @property
    def duration_s(self) -> float:
        return self._written / SAMPLE_RATE

    def write(self, frame: AudioFrame) -> None:
        with self._lock:
            if self._wav is None:
                return
            start = max(0, round(frame.t_start * SAMPLE_RATE))
            gap = start - self._written
            if 0 < gap <= _MAX_GAP_S * SAMPLE_RATE:
                self._wav.writeframes(np.zeros(gap, dtype=np.int16).tobytes())
                self._written += gap
            samples = frame.samples
            if gap < 0:
                # Frame overlaps what we already wrote (callback jitter): keep only the new tail.
                samples = samples[min(len(samples), -gap):]
            if len(samples):
                self._wav.writeframes(float_to_int16(samples).tobytes())
                self._written += len(samples)

    def close(self) -> None:
        with self._lock:
            if self._wav is not None:
                self._wav.close()
                self._wav = None
