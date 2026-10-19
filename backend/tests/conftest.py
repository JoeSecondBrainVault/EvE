"""Shared fakes: no microphone, GPU or model download needed for the unit/API suite."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from eve.audio.types import SAMPLE_RATE, SOURCE_ME, SOURCE_THEM, AudioFrame
from eve.config import Settings
from eve.main import Components
from eve.stt.transcriber import TranscribedText


class EnergyVAD:
    """Fake VAD: 'speech' when RMS is high. Lets tests synthesize speech with noise bursts."""

    def __call__(self, window: np.ndarray) -> float:
        return 1.0 if float(np.sqrt(np.mean(window**2))) > 0.05 else 0.0

    def reset(self) -> None:
        pass


class FakeSTT:
    device = "cpu"

    def __init__(self, text_for: Callable[[np.ndarray], str | None] | None = None) -> None:
        self._text_for = text_for or (lambda s: f"utterance of {len(s) / SAMPLE_RATE:.1f}s")

    def transcribe(self, samples: np.ndarray) -> TranscribedText | None:
        text = self._text_for(samples)
        return TranscribedText(text, "en", -0.2) if text else None


class FakeCapture:
    """Pushes a scripted list of frames from a background thread, like WASAPI callbacks."""

    sources = [SOURCE_THEM, SOURCE_ME]

    def __init__(self, frames: list[AudioFrame]) -> None:
        self._frames = frames
        self._thread: threading.Thread | None = None
        self.started = threading.Event()
        self.finished = threading.Event()

    def start(self, on_frame) -> None:
        def run() -> None:
            self.started.set()
            for f in self._frames:
                on_frame(f)
            self.finished.set()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread:
            self._thread.join(timeout=5)


def speech_then_silence(source: str, t_start: float, speech_s: float, silence_s: float,
                        chunk_s: float = 0.1) -> list[AudioFrame]:
    """Frames of loud noise ('speech') followed by silence, in chunk_s pieces."""
    rng = np.random.default_rng(0)
    frames: list[AudioFrame] = []
    t = t_start
    for dur, loud in ((speech_s, True), (silence_s, False)):
        n_chunks = round(dur / chunk_s)
        for _ in range(n_chunks):
            n = round(chunk_s * SAMPLE_RATE)
            samples = (rng.uniform(-0.5, 0.5, n) if loud else np.zeros(n)).astype(np.float32)
            t += chunk_s
            frames.append(AudioFrame(source, samples, t))
    return frames


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", port=8765,
                    _env_file=None)


@pytest.fixture
def frames() -> list[AudioFrame]:
    return speech_then_silence(SOURCE_THEM, 0.0, 1.5, 1.0)


@pytest.fixture
def make_components() -> Callable[..., Components]:
    def factory(frames: list[AudioFrame] | None = None, stt: FakeSTT | None = None) -> Components:
        holder: dict[str, FakeCapture] = {}

        def capture_factory(_s: Settings):
            def make(_clock):
                holder["capture"] = FakeCapture(frames or [])
                return holder["capture"]
            return make

        comps = Components(
            load_stt=lambda _s: stt or FakeSTT(),
            capture_factory=capture_factory,
            vad_factory=EnergyVAD,
            list_devices=lambda: [{"index": 0, "name": "Fake", "is_loopback": True,
                                   "max_input_channels": 2, "default_sample_rate": 48000.0}],
        )
        comps.holder = holder  # type: ignore[attr-defined]
        return comps

    return factory
