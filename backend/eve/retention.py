"""Retention cleaner & API rate-limiting utilities.

1. Audio Retention: Scans `recordings_dir` and purges raw WAV files older than N days
   while preserving SQLite transcripts, RAG embeddings, and Obsidian notes.
2. Rate Limiting: In-memory sliding-window request rate limiter protecting LLM routes.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from pathlib import Path

from eve.config import Settings, get_settings

logger = logging.getLogger(__name__)


def purge_expired_recordings(
    recordings_dir: Path,
    retention_days: int = 30,
) -> tuple[int, int]:
    """Purges raw WAV files in session folders older than retention_days.
    
    Returns:
        (purged_files_count, freed_bytes)
    """
    if not recordings_dir.exists():
        return (0, 0)

    now = time.time()
    cutoff_seconds = retention_days * 86400.0
    purged_count = 0
    freed_bytes = 0

    for session_folder in recordings_dir.iterdir():
        if not session_folder.is_dir():
            continue

        try:
            mtime = session_folder.stat().st_mtime
            if (now - mtime) > cutoff_seconds:
                for wav in session_folder.glob("*.wav"):
                    size = wav.stat().st_size
                    wav.unlink()
                    purged_count += 1
                    freed_bytes += size
                    logger.info("Purged expired recording %s (%d bytes)", wav, size)
        except Exception as exc:
            logger.debug("Error inspecting recording folder %s: %s", session_folder, exc)

    return (purged_count, freed_bytes)


class SlidingWindowRateLimiter:
    """Thread-safe sliding window in-memory rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str) -> bool:
        """Returns True if the request is permitted under the rate limit."""
        with self._lock:
            now = time.time()
            q = self._history[client_id]

            # Evict timestamps outside current window
            cutoff = now - self.window_seconds
            while q and q[0] < cutoff:
                q.popleft()

            if len(q) < self.max_requests:
                q.append(now)
                return True

            return False

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
