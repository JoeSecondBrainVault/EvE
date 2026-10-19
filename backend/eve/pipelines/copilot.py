"""Live Copilot: rolling 3-minute transcript analyzer & real-time study talking point suggester.

Maintains a non-intrusive rolling context of the active call, detects professor questions,
retrieves relevant knowledge from past lectures via Hybrid RAG, and streams concise bulleted
talking points directly to the dashboard WebSocket (text-only, never speaks into call).
"""

from __future__ import annotations

import collections
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from eve.config import Settings, get_settings
from eve.events import EventBus
from eve.llm.router import LLMRouter

logger = logging.getLogger(__name__)

COPILOT_SYSTEM_PROMPT = """You are the silent, real-time Live Copilot for Joe, an IT student attending class.
Review the recent rolling transcript of the lecture. If the professor or speaker asked a question, raised a problem, or introduced a core concept:
1. Identify the topic/question being discussed.
2. Provide 2 to 3 concise, high-value bulleted talking points or direct answer hints drawn from the lecture and past study notes.
3. Keep each talking point to ONE clear sentence so the student can glance at it and speak or take notes immediately.
"""

QUESTION_DETECTION_REGEX = re.compile(
    r"(\?|who\b|what\b|when\b|where\b|why\b|how\b|unsa\b|ngano\b|ano\b|bakit\b|can anyone\b|explain\b|define\b|differentiate\b)",
    re.IGNORECASE,
)


class CopilotItem(BaseModel):
    topic: str = Field(description="The core question or topic identified from the call.")
    talking_points: list[str] = Field(
        description="2 to 3 concise, actionable talking points or answer hints for the student.",
    )
    context_summary: str = Field(
        description="One-line summary of what the speaker just said.",
    )


class TranscriptSnippet(BaseModel):
    source: str
    text: str
    t0: float
    t1: float


class LiveCopilot:
    """Manages a rolling lecture transcript window and generates real-time dashboard suggestions."""

    def __init__(
        self,
        engine: Any,
        router: LLMRouter,
        settings: Settings | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.engine = engine
        self.router = router
        self.settings = settings or get_settings()
        self.event_bus = event_bus
        self.window_seconds = float(self.settings.copilot_window_s)
        self._history: collections.deque[TranscriptSnippet] = collections.deque()
        self._last_suggestion: CopilotItem | None = None

    def add_segment(self, source: str, text: str, t0: float, t1: float) -> None:
        """Adds a speech segment into the rolling window and purges expired entries."""
        snippet = TranscriptSnippet(source=source, text=text, t0=t0, t1=t1)
        self._history.append(snippet)

        # Evict segments that fall outside the rolling window
        current_time = t1
        while self._history and (current_time - self._history[0].t1 > self.window_seconds):
            self._history.popleft()

    def get_window_text(self) -> str:
        """Returns the formatted rolling transcript for the current window."""
        return "\n".join(f"[{s.source.upper()} {s.t0:.1f}s]: {s.text}" for s in self._history)

    def should_trigger(self, new_text: str) -> bool:
        """Heuristic check to determine if incoming text represents a question or prompt."""
        return bool(QUESTION_DETECTION_REGEX.search(new_text))

    def generate_suggestion(self, prompt_hint: str | None = None) -> CopilotItem | None:
        """Generates real-time talking points using rolling context and past lecture RAG."""
        if not self._history and not prompt_hint:
            return None

        transcript_window = self.get_window_text()

        # Retrieve relevant past notes via RAG if question is apparent
        rag_context = ""
        try:
            from eve.rag.chat import HybridRAGSearcher
            from eve.rag.embeddings import EmbeddingEngine

            emb_engine = EmbeddingEngine(self.settings)
            searcher = HybridRAGSearcher(self.engine, emb_engine)
            search_query = prompt_hint or (self._history[-1].text if self._history else "")
            if search_query:
                chunks = searcher.search(search_query, top_k=2)
                if chunks:
                    rag_context = "\n\nRelevant past lecture excerpts:\n" + "\n".join(
                        f"- ({c.course_name or 'General'}) {c.text}" for c in chunks
                    )
        except Exception as exc:
            logger.debug("RAG lookup in copilot skipped: %s", exc)

        prompt = (
            f"Recent rolling transcript (last {int(self.window_seconds)}s):\n{transcript_window}"
            f"{rag_context}\n\n"
            f"User focus hint: {prompt_hint or 'Detect any question or key concept and provide talking points.'}"
        )

        try:
            suggestion, provider = self.router.generate_structured(
                prompt=prompt,
                system_prompt=COPILOT_SYSTEM_PROMPT,
                schema=CopilotItem,
            )
            self._last_suggestion = suggestion

            # Publish suggestion to WebSocket subscribers
            if self.event_bus:
                self.event_bus.publish({
                    "type": "copilot_suggestion",
                    "data": suggestion.model_dump(),
                })

            return suggestion
        except Exception as exc:
            logger.error("Live Copilot suggestion generation failed: %s", exc)
            return None

    @property
    def last_suggestion(self) -> CopilotItem | None:
        return self._last_suggestion

    def clear(self) -> None:
        self._history.clear()
        self._last_suggestion = None
