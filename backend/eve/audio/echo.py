"""Echo de-duplication between system audio ("them") and the microphone ("me").

Without headphones, the mic re-captures the speakers, so every professor sentence would
appear twice (once as "them", once as "me"). A mic utterance is dropped when it overlaps
a recent loopback utterance in time and its text is near-identical.
"""

from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher

from eve.audio.types import SOURCE_ME, SOURCE_THEM

_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize(text: str) -> str:
    return " ".join(_WORD.sub(" ", text.lower()).split())


@dataclass(slots=True)
class _Recent:
    t0: float
    t1: float
    text: str


class EchoFilter:
    def __init__(self, similarity: float = 0.6, window: int = 20) -> None:
        self._similarity = similarity
        self._recent: deque[_Recent] = deque(maxlen=window)
        self._lock = threading.Lock()

    def accept(self, source: str, t0: float, t1: float, text: str) -> bool:
        norm = _normalize(text)
        with self._lock:
            if source == SOURCE_THEM:
                self._recent.append(_Recent(t0, t1, norm))
                return True
            if source != SOURCE_ME or not norm:
                return bool(norm)
            for prev in self._recent:
                overlap = min(t1, prev.t1) - max(t0, prev.t0)
                if overlap <= 0:
                    continue
                if SequenceMatcher(None, norm, prev.text).ratio() >= self._similarity:
                    return False
            return True
