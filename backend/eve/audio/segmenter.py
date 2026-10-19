"""Streaming voice-activity segmentation.

``SpeechSegmenter`` turns a continuous stream of 16 kHz frames into utterances using any
``VoiceProbability`` model (Silero ONNX in production, a fake in tests). Logic:

* speech starts when p >= threshold; 300 ms of pre-roll is kept so first syllables aren't cut
* speech ends after ``min_silence_s`` below ``threshold - 0.15`` (hysteresis)
* utterances are force-split at ``max_utterance_s`` so live captions stay responsive
* utterances shorter than ``min_utterance_s`` are dropped (coughs, clicks)
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

import numpy as np

from eve.audio.types import SAMPLE_RATE, AudioFrame, Utterance

WINDOW = 512  # Silero v5/v6 window at 16 kHz (32 ms)
_PRE_ROLL_WINDOWS = 10  # ~320 ms


class VoiceProbability(Protocol):
    def __call__(self, window: np.ndarray) -> float: ...
    def reset(self) -> None: ...


class SpeechSegmenter:
    def __init__(
        self,
        source: str,
        vad: VoiceProbability,
        *,
        threshold: float = 0.5,
        min_silence_s: float = 0.6,
        max_utterance_s: float = 15.0,
        min_utterance_s: float = 0.4,
    ) -> None:
        self.source = source
        self._vad = vad
        self._on = threshold
        self._off = max(0.05, threshold - 0.15)
        self._silence_windows = max(1, round(min_silence_s * SAMPLE_RATE / WINDOW))
        self._max_samples = int(max_utterance_s * SAMPLE_RATE)
        self._min_samples = int(min_utterance_s * SAMPLE_RATE)

        self._pending = np.zeros(0, dtype=np.float32)
        self._pending_t = 0.0  # session time of _pending[0]
        self._last_frame_end: float | None = None
        self._pre_roll: deque[tuple[float, np.ndarray]] = deque(maxlen=_PRE_ROLL_WINDOWS)
        self._speech: list[np.ndarray] = []
        self._speech_t0 = 0.0
        self._speech_len = 0
        self._silent_run = 0
        self._last_voiced_end = 0  # samples into the utterance at last voiced window

    @property
    def in_speech(self) -> bool:
        return bool(self._speech)

    def feed(self, frame: AudioFrame) -> list[Utterance]:
        out: list[Utterance] = []
        start = frame.t_start
        frame_end = start + len(frame.samples) / SAMPLE_RATE

        if self._last_frame_end is not None and (start - self._last_frame_end) > 0.25:
            # Discontinuity (loopback went quiet and produced no callbacks): close any utterance.
            if self._speech:
                out.extend(self._finish())
            self._vad.reset()
            self._pre_roll.clear()
            self._pending = frame.samples.astype(np.float32, copy=False)
            self._pending_t = start
        else:
            if len(self._pending) == 0:
                self._pending_t = start
            self._pending = np.concatenate([self._pending, frame.samples.astype(np.float32, copy=False)])

        self._last_frame_end = frame_end

        n_windows = len(self._pending) // WINDOW
        for i in range(n_windows):
            window = self._pending[i * WINDOW:(i + 1) * WINDOW]
            t = self._pending_t + i * WINDOW / SAMPLE_RATE
            out.extend(self._step(window, t))
        consumed = n_windows * WINDOW
        self._pending = self._pending[consumed:]
        self._pending_t += consumed / SAMPLE_RATE
        return out

    def flush(self) -> list[Utterance]:
        out = self._finish() if self._speech else []
        self._vad.reset()
        self._pre_roll.clear()
        self._pending = np.zeros(0, dtype=np.float32)
        return out

    def _step(self, window: np.ndarray, t: float) -> list[Utterance]:
        p = float(self._vad(window))
        if not self._speech:
            if p >= self._on:
                pre = list(self._pre_roll)
                self._speech = [w for _, w in pre] + [window]
                self._speech_t0 = pre[0][0] if pre else t
                self._speech_len = sum(len(w) for w in self._speech)
                self._last_voiced_end = self._speech_len
                self._silent_run = 0
                self._pre_roll.clear()
            else:
                self._pre_roll.append((t, window))
            return []

        self._speech.append(window)
        self._speech_len += len(window)
        if p >= self._off:
            self._silent_run = 0
            self._last_voiced_end = self._speech_len
        else:
            self._silent_run += 1

        if self._silent_run >= self._silence_windows or self._speech_len >= self._max_samples:
            return self._finish()
        return []

    def _finish(self) -> list[Utterance]:
        audio = np.concatenate(self._speech)
        # Trim trailing silence but keep ~200 ms tail so Whisper sees word endings.
        keep = min(len(audio), self._last_voiced_end + int(0.2 * SAMPLE_RATE))
        audio = audio[:keep]
        t0 = self._speech_t0
        self._speech = []
        self._speech_len = 0
        self._silent_run = 0
        self._last_voiced_end = 0
        if len(audio) < self._min_samples:
            return []
        return [Utterance(self.source, t0, t0 + len(audio) / SAMPLE_RATE, audio)]
