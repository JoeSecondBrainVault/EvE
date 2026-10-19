"""Silero VAD ONNX streaming wrapper.

Uses the Silero VAD ONNX model bundled with faster-whisper (no PyTorch install needed).
Maintains streaming context (64 samples) and RNN hidden states across 512-sample (32 ms)
windows at 16 kHz. Falls back to an energy-based estimator if ONNX runtime is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

WINDOW_SIZE = 512       # 32 ms at 16 kHz
CONTEXT_SIZE = 64       # Silero streaming context window


class SileroVAD:
    """Voice Activity Detector satisfying the ``VoiceProbability`` protocol."""

    def __init__(self, model_path: Path | None = None) -> None:
        self._session: Any = None
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SIZE), dtype=np.float32)
        self._init_session(model_path)

    def _init_session(self, model_path: Path | None) -> None:
        try:
            import onnxruntime as ort

            path = model_path
            if path is None:
                from faster_whisper.utils import get_assets_path

                path = Path(get_assets_path()) / "silero_vad.onnx"

            if path.exists():
                opts = ort.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                opts.enable_cpu_mem_arena = False
                opts.log_severity_level = 4
                self._session = ort.InferenceSession(
                    str(path),
                    providers=["CPUExecutionProvider"],
                    sess_options=opts,
                )
                log.info("Silero VAD initialized from %s", path)
            else:
                log.warning("Silero VAD model not found at %s; using energy fallback", path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Silero VAD onnx init failed (%s); using energy fallback", exc)
            self._session = None

    def reset(self) -> None:
        """Reset internal recurrent state between disjoint audio utterances."""
        self._h.fill(0.0)
        self._c.fill(0.0)
        self._context.fill(0.0)

    def __call__(self, window: np.ndarray) -> float:
        """Estimate speech probability for a 512-sample float32 window."""
        if len(window) != WINDOW_SIZE:
            # Pad or truncate window to exactly WINDOW_SIZE
            if len(window) < WINDOW_SIZE:
                padded = np.zeros(WINDOW_SIZE, dtype=np.float32)
                padded[:len(window)] = window
                window = padded
            else:
                window = window[:WINDOW_SIZE]

        if self._session is None:
            # Energy fallback (RMS thresholding mapped into [0, 1])
            rms = float(np.sqrt(np.mean(window ** 2)))
            return min(1.0, max(0.0, (rms - 0.01) / 0.08))

        # Silero VAD takes [context + window] of shape (1, 576)
        batched = np.concatenate([self._context, window.reshape(1, -1)], axis=1).astype(np.float32)
        try:
            out, h, c = self._session.run(
                None,
                {"input": batched, "h": self._h, "c": self._c},
            )
            self._h = h
            self._c = c
            self._context = window[-CONTEXT_SIZE:].reshape(1, -1).astype(np.float32)
            return float(out[0, 0])
        except Exception:  # noqa: BLE001
            # If model inference fails on a frame, return energy estimate
            rms = float(np.sqrt(np.mean(window ** 2)))
            return min(1.0, max(0.0, (rms - 0.01) / 0.08))
