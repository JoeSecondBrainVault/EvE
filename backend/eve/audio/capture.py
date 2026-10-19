"""WASAPI loopback and microphone audio capture using PyAudioWPatch.

Captures system audio (Zoom, Google Meet, Teams, Discord, YouTube) via WASAPI loopback ("them")
and the active microphone ("me"). Audio is resampled from the hardware's native sample rate
(typically 44.1 kHz or 48 kHz) to 16 kHz mono float32 for Whisper and Silero VAD.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from eve.audio.types import (
    SAMPLE_RATE,
    SOURCE_ME,
    SOURCE_THEM,
    AudioFrame,
    int16_bytes_to_mono_float,
)

log = logging.getLogger(__name__)


def list_devices() -> list[dict[str, Any]]:
    """List available audio devices on Windows, tagging loopback and default devices."""
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        try:
            import pyaudio
        except ImportError:
            return []

    pa = pyaudio.PyAudio()
    devices: list[dict[str, Any]] = []
    try:
        wasapi_api_idx = None
        for i in range(pa.get_host_api_count()):
            api_info = pa.get_host_api_info_by_index(i)
            if "WASAPI" in api_info.get("name", "").upper():
                wasapi_api_idx = i
                break

        default_loopback_idx = None
        if hasattr(pa, "get_default_wasapi_loopback"):
            try:
                loop = pa.get_default_wasapi_loopback()
                if loop:
                    default_loopback_idx = loop.get("index")
            except Exception:  # noqa: BLE001
                pass

        default_input_idx = None
        try:
            default_in = pa.get_default_input_device_info()
            if default_in:
                default_input_idx = default_in.get("index")
        except Exception:  # noqa: BLE001
            pass

        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
                is_loopback = bool(info.get("isLoopbackDevice", False))
                is_default = (i == default_loopback_idx) if is_loopback else (i == default_input_idx)
                devices.append({
                    "index": i,
                    "name": info.get("name", "Unknown"),
                    "is_loopback": is_loopback,
                    "is_default": is_default,
                    "max_input_channels": info.get("maxInputChannels", 0),
                    "max_output_channels": info.get("maxOutputChannels", 0),
                    "default_sample_rate": float(info.get("defaultSampleRate", 48000)),
                    "host_api": pa.get_host_api_info_by_index(info.get("hostApi", 0)).get("name", ""),
                })
            except Exception:  # noqa: BLE001
                continue
    finally:
        pa.terminate()

    return devices


class _Resampler:
    """Resample from hardware rate to 16,000 Hz using soxr or linear interpolation."""

    def __init__(self, in_rate: int, out_rate: int = SAMPLE_RATE) -> None:
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._soxr = None
        if in_rate != out_rate:
            try:
                import soxr

                self._soxr = soxr.ResampleStream(in_rate, out_rate, num_channels=1, quality="QQ")
            except Exception:  # noqa: BLE001
                self._soxr = None

    def resample(self, samples: np.ndarray) -> np.ndarray:
        if self.in_rate == self.out_rate or len(samples) == 0:
            return samples
        if self._soxr is not None:
            return self._soxr.resample_chunk(samples).astype(np.float32, copy=False)
        # Fast numpy linear interpolation fallback
        orig_len = len(samples)
        target_len = int(round(orig_len * (self.out_rate / self.in_rate)))
        if target_len == 0:
            return np.zeros(0, dtype=np.float32)
        indices = np.linspace(0, orig_len - 1, target_len)
        return np.interp(indices, np.arange(orig_len), samples).astype(np.float32)


class WasapiCapture:
    """Manages two PyAudio streams: loopback ("them") and mic ("me")."""

    def __init__(
        self,
        clock: Callable[[], float],
        *,
        loopback: bool = True,
        mic: bool = True,
    ) -> None:
        self._clock = clock
        self._want_loopback = loopback
        self._want_mic = mic
        self._sources: list[str] = []
        if loopback:
            self._sources.append(SOURCE_THEM)
        if mic:
            self._sources.append(SOURCE_ME)

        self._pa: Any = None
        self._streams: list[Any] = []
        self._lock = threading.Lock()
        self._on_frame: Callable[[AudioFrame], None] | None = None

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    def start(self, on_frame: Callable[[AudioFrame], None]) -> None:
        import pyaudiowpatch as pyaudio

        self._on_frame = on_frame
        pa = pyaudio.PyAudio()
        self._pa = pa
        streams = []

        try:
            # 1. System loopback capture ("them")
            if self._want_loopback:
                try:
                    dev = pa.get_default_wasapi_loopback()
                    if dev:
                        rate = int(dev.get("defaultSampleRate", 48000))
                        channels = min(2, dev.get("maxInputChannels", 2) or 2)
                        resampler = _Resampler(rate, SAMPLE_RATE)

                        def loopback_cb(in_data, _frame_count, _time_info, _status):
                            t_end = self._clock()
                            mono = int16_bytes_to_mono_float(in_data, channels)
                            samples_16k = resampler.resample(mono)
                            if self._on_frame and len(samples_16k):
                                self._on_frame(AudioFrame(SOURCE_THEM, samples_16k, t_end))
                            return (None, pyaudio.paContinue)

                        stream = pa.open(
                            format=pyaudio.paInt16,
                            channels=channels,
                            rate=rate,
                            input=True,
                            input_device_index=dev["index"],
                            stream_callback=loopback_cb,
                            frames_per_buffer=1024,
                        )
                        streams.append(stream)
                        log.info("WASAPI loopback capture opened on %s (%d Hz)", dev.get("name"), rate)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not open WASAPI loopback: %s", exc)

            # 2. Microphone capture ("me")
            if self._want_mic:
                try:
                    dev = pa.get_default_input_device_info()
                    if dev:
                        rate = int(dev.get("defaultSampleRate", 48000))
                        channels = min(1, dev.get("maxInputChannels", 1) or 1)
                        resampler = _Resampler(rate, SAMPLE_RATE)

                        def mic_cb(in_data, _frame_count, _time_info, _status):
                            t_end = self._clock()
                            mono = int16_bytes_to_mono_float(in_data, channels)
                            samples_16k = resampler.resample(mono)
                            if self._on_frame and len(samples_16k):
                                self._on_frame(AudioFrame(SOURCE_ME, samples_16k, t_end))
                            return (None, pyaudio.paContinue)

                        stream = pa.open(
                            format=pyaudio.paInt16,
                            channels=channels,
                            rate=rate,
                            input=True,
                            input_device_index=dev["index"],
                            stream_callback=mic_cb,
                            frames_per_buffer=1024,
                        )
                        streams.append(stream)
                        log.info("Microphone capture opened on %s (%d Hz)", dev.get("name"), rate)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not open microphone capture: %s", exc)

            if not streams:
                raise RuntimeError("Failed to open any audio capture stream (neither loopback nor mic).")

            for stream in streams:
                stream.start_stream()
            self._streams = streams
        except Exception:
            for s in streams:
                try:
                    s.stop_stream()
                    s.close()
                except Exception:  # noqa: BLE001
                    pass
            pa.terminate()
            self._pa = None
            raise

    def stop(self) -> None:
        with self._lock:
            for stream in self._streams:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
            self._streams.clear()
            if self._pa is not None:
                try:
                    self._pa.terminate()
                except Exception:  # noqa: BLE001
                    pass
                self._pa = None
