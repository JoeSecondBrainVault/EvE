"""Thread-safe pub/sub bus bridging audio/STT worker threads to asyncio WebSocket clients."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

Event = dict[str, Any]


class EventBus:
    def __init__(self, loop: asyncio.AbstractEventLoop, max_queue: int = 256) -> None:
        self._loop = loop
        self._max_queue = max_queue
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def publish(self, event: Event) -> None:
        """Publish from any thread. Never blocks the caller (audio/STT threads)."""
        self._loop.call_soon_threadsafe(self._fan_out, event)

    def _fan_out(self, event: Event) -> None:
        for queue in self._subscribers:
            if queue.full():
                # Slow client: drop its oldest event rather than stall everyone.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
