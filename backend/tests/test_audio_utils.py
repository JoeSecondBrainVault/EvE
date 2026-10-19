import wave

import numpy as np

from eve.audio.echo import EchoFilter
from eve.audio.recorder import AlignedWavRecorder
from eve.audio.types import SAMPLE_RATE, SOURCE_ME, SOURCE_THEM, AudioFrame, int16_bytes_to_mono_float
from eve.config import Settings
from eve.session import safe_folder_name


def _read(path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def test_recorder_pads_gaps_so_file_time_matches_session_time(tmp_path):
    rec = AlignedWavRecorder(tmp_path / "them.wav")
    one = np.full(SAMPLE_RATE, 0.5, dtype=np.float32)
    rec.write(AudioFrame(SOURCE_THEM, one, t_end=1.0))  # covers 0-1 s
    rec.write(AudioFrame(SOURCE_THEM, one, t_end=4.0))  # covers 3-4 s, 2 s of silence before
    rec.close()
    rate, data = _read(tmp_path / "them.wav")
    assert rate == SAMPLE_RATE
    assert len(data) == 4 * SAMPLE_RATE
    assert np.all(data[SAMPLE_RATE:3 * SAMPLE_RATE] == 0)
    assert data[3 * SAMPLE_RATE + 10] > 10000


def test_recorder_trims_overlapping_jitter(tmp_path):
    rec = AlignedWavRecorder(tmp_path / "me.wav")
    rec.write(AudioFrame(SOURCE_ME, np.ones(SAMPLE_RATE, np.float32) * 0.1, t_end=1.0))
    rec.write(AudioFrame(SOURCE_ME, np.ones(SAMPLE_RATE, np.float32) * 0.1, t_end=1.5))  # overlaps 0.5 s
    rec.close()
    assert len(_read(tmp_path / "me.wav")[1]) == int(1.5 * SAMPLE_RATE)


def test_echo_filter_drops_mic_copy_of_speaker_audio():
    f = EchoFilter()
    assert f.accept(SOURCE_THEM, 10.0, 13.0, "Ang deadline sa assignment kay sa Friday.")
    assert not f.accept(SOURCE_ME, 10.1, 13.2, "ang deadline sa assignment kay sa friday")
    assert f.accept(SOURCE_ME, 10.5, 12.0, "Sir, pwede ko mangutana?")  # different words: real
    assert f.accept(SOURCE_ME, 20.0, 22.0, "Ang deadline sa assignment kay sa Friday.")  # no overlap


def test_int16_stereo_downmix():
    stereo = np.array([32767, -32768, 16384, 16384], dtype=np.int16).tobytes()
    mono = int16_bytes_to_mono_float(stereo, channels=2)
    assert mono.dtype == np.float32
    assert np.allclose(mono, [0.0, 0.5], atol=1e-3)


def test_safe_folder_name_blocks_traversal():
    assert safe_folder_name("../../Windows/System32") == "WindowsSystem32"
    assert safe_folder_name("..\\..\\boot") == "boot"
    assert safe_folder_name("???") == "session"


def test_settings_reject_non_loopback_host(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        Settings(host="0.0.0.0", data_dir=tmp_path, _env_file=None)  # nosec B104 - testing rejection of 0.0.0.0


def test_empty_language_means_autodetect(tmp_path):
    s = Settings(language="  ", data_dir=tmp_path, _env_file=None)
    assert s.language is None
    assert "Bisaya" not in s.initial_prompt  # prompt is example speech, not instructions
    assert "karon" in s.initial_prompt
