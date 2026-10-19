import numpy as np

from conftest import EnergyVAD, speech_then_silence
from eve.audio.segmenter import SpeechSegmenter
from eve.audio.types import SAMPLE_RATE, SOURCE_THEM, AudioFrame


def run(seg: SpeechSegmenter, frames):
    out = []
    for f in frames:
        out.extend(seg.feed(f))
    return out


def test_single_utterance_detected_with_correct_timing():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD(), min_silence_s=0.6)
    utts = run(seg, speech_then_silence(SOURCE_THEM, 0.0, 2.0, 1.0))
    assert len(utts) == 1
    u = utts[0]
    assert u.t0 == 0.0  # speech starts at 0, pre-roll can't go negative
    assert 1.9 <= u.t1 - u.t0 <= 2.3  # 2 s speech + <=200 ms tail
    assert u.source == SOURCE_THEM


def test_short_noise_is_dropped():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD(), min_utterance_s=0.4)
    assert run(seg, speech_then_silence(SOURCE_THEM, 0.0, 0.1, 1.0)) == []


def test_long_speech_is_force_split():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD(), max_utterance_s=3.0)
    utts = run(seg, speech_then_silence(SOURCE_THEM, 0.0, 7.0, 1.0)) + seg.flush()
    assert len(utts) >= 3
    assert all(u.t1 - u.t0 <= 3.05 for u in utts)
    # contiguous coverage: each chunk starts where the previous ended (within one window)
    for a, b in zip(utts, utts[1:]):
        assert abs(b.t0 - a.t1) < 0.25


def test_flush_emits_in_progress_speech():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD())
    assert run(seg, speech_then_silence(SOURCE_THEM, 0.0, 1.0, 0.0)) == []
    assert len(seg.flush()) == 1


def test_gap_in_loopback_callbacks_closes_utterance():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD())
    first = speech_then_silence(SOURCE_THEM, 0.0, 1.0, 0.0)
    # loopback goes quiet (no callbacks) for 5 s, then new speech arrives
    later = speech_then_silence(SOURCE_THEM, 6.0, 1.0, 1.0)
    utts = run(seg, first + later)
    assert len(utts) == 2
    assert utts[1].t0 >= 6.0


def test_pre_roll_keeps_leading_audio():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD())
    frames = speech_then_silence(SOURCE_THEM, 0.0, 0.0, 1.0) + speech_then_silence(SOURCE_THEM, 1.0, 1.0, 1.0)
    utts = run(seg, frames)
    assert len(utts) == 1
    assert 0.6 <= utts[0].t0 < 1.0  # ~320 ms of pre-roll before the onset at 1.0 s


def test_odd_frame_sizes_are_buffered():
    seg = SpeechSegmenter(SOURCE_THEM, EnergyVAD())
    rng = np.random.default_rng(1)
    t, out = 0.0, []
    for n in [100, 700, 1234, 333] * 20:  # ~1.5 s of loud audio in jittery chunks
        t += n / SAMPLE_RATE
        out += seg.feed(AudioFrame(SOURCE_THEM, rng.uniform(-0.5, 0.5, n).astype(np.float32), t))
    out += seg.flush()
    assert len(out) == 1
