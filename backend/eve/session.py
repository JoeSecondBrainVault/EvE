"""Session orchestration: capture -> recorder + VAD -> STT worker -> DB + live events."""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession
from sqlmodel import select

from eve.audio.echo import EchoFilter
from eve.audio.recorder import AlignedWavRecorder
from eve.audio.segmenter import SpeechSegmenter, VoiceProbability
from eve.audio.types import AudioFrame, Utterance
from eve.config import Settings
from eve.events import EventBus
from eve.models import Course, Segment, Session, utcnow
from eve.stt.transcriber import SpeechToText

log = logging.getLogger(__name__)

_STOP = object()
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


class CaptureSource(Protocol):
    sources: list[str]

    def start(self, on_frame: Callable[[AudioFrame], None]) -> None: ...
    def stop(self) -> None: ...


CaptureFactory = Callable[[Callable[[], float]], CaptureSource]  # receives the session clock


class SessionError(RuntimeError):
    """Raised for user-facing session state errors (mapped to HTTP 4xx)."""


@dataclass
class _Active:
    session_id: int
    started: float
    capture: CaptureSource
    recorders: dict[str, AlignedWavRecorder]
    segmenters: dict[str, SpeechSegmenter]
    work: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=500))
    worker: threading.Thread | None = None
    dropped: int = 0


def safe_folder_name(text: str, fallback: str = "session") -> str:
    cleaned = _SAFE_NAME.sub("", text).strip(" .")[:60]
    return cleaned or fallback


class SessionManager:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        bus: EventBus,
        *,
        stt: Callable[[], SpeechToText | None],
        capture_factory: CaptureFactory,
        vad_factory: Callable[[], VoiceProbability],
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._bus = bus
        self._stt = stt
        self._capture_factory = capture_factory
        self._vad_factory = vad_factory
        self._lock = threading.Lock()
        self._active: _Active | None = None
        self._echo = EchoFilter()

    @property
    def active_session_id(self) -> int | None:
        active = self._active
        return active.session_id if active else None

    # ------------------------------------------------------------------ lifecycle
    def start(self, *, title: str, course: str | None = None, consent_confirmed: bool = True) -> Session:
        if not consent_confirmed:
            raise SessionError("Recording requires confirming that participants are informed.")
        stt = self._stt()
        if stt is None:
            raise SessionError("Speech model is still loading. Try again in a moment.")
        with self._lock:
            if self._active is not None:
                raise SessionError(f"Session {self._active.session_id} is already recording.")

            with DBSession(self._engine) as db:
                course_row = self._get_or_create_course(db, course) if course else None
                row = Session(
                    title=title.strip()[:200] or "Untitled session",
                    course_id=course_row.id if course_row else None,
                    consent_confirmed=True,
                )
                db.add(row)
                db.commit()
                db.refresh(row)

            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            rec_dir: Path = self._settings.recordings_dir / f"{stamp}-{row.id}-{safe_folder_name(row.title)}"
            started = time.monotonic()

            def clock() -> float:
                return time.monotonic() - started

            capture = self._capture_factory(clock)
            s = self._settings
            active = _Active(
                session_id=row.id,
                started=started,
                capture=capture,
                recorders={src: AlignedWavRecorder(rec_dir / f"{src}.wav") for src in capture.sources},
                segmenters={
                    src: SpeechSegmenter(
                        src,
                        self._vad_factory(),
                        threshold=s.vad_threshold,
                        min_silence_s=s.vad_min_silence_s,
                        max_utterance_s=s.vad_max_utterance_s,
                        min_utterance_s=s.vad_min_utterance_s,
                    )
                    for src in capture.sources
                },
            )
            active.worker = threading.Thread(
                target=self._stt_loop, args=(active, stt), name=f"stt-{row.id}", daemon=True
            )
            active.worker.start()
            try:
                capture.start(lambda frame: self._on_frame(active, frame))
            except Exception as exc:
                active.work.put(_STOP)
                active.worker.join(timeout=5)
                for rec in active.recorders.values():
                    rec.close()
                with DBSession(self._engine) as db:
                    failed_row = db.get(Session, row.id)
                    if failed_row:
                        db.delete(failed_row)
                        db.commit()
                raise SessionError(f"Could not open audio devices: {exc}") from exc

            with DBSession(self._engine) as db:
                db_row = db.get(Session, row.id)
                db_row.recording_dir = str(rec_dir)
                db.add(db_row)
                db.commit()
                db.refresh(db_row)
                row = db_row
            self._active = active

        self._bus.publish({"type": "session_started", "session_id": row.id, "title": row.title,
                           "sources": capture.sources, "device": stt.device})
        return row

    def stop(self) -> Session:
        with self._lock:
            active = self._active
            if active is None:
                raise SessionError("No session is recording.")
            self._active = None
        active.capture.stop()
        for seg in active.segmenters.values():
            for utt in seg.flush():
                self._enqueue(active, utt)
        active.work.put(_STOP)
        if active.worker:
            active.worker.join()
        for rec in active.recorders.values():
            rec.close()
        row = self._mark(active.session_id, status="stopped", ended_at=utcnow())
        self._bus.publish({"type": "session_stopped", "session_id": active.session_id,
                           "dropped_utterances": active.dropped})
        return row

    def shutdown(self) -> None:
        if self._active is not None:
            try:
                self.stop()
            except SessionError:
                pass

    # ------------------------------------------------------------------ pipeline
    def _on_frame(self, active: _Active, frame: AudioFrame) -> None:
        rec = active.recorders.get(frame.source)
        seg = active.segmenters.get(frame.source)
        if rec is None or seg is None:
            return
        rec.write(frame)
        for utt in seg.feed(frame):
            self._enqueue(active, utt)

    def _enqueue(self, active: _Active, utt: Utterance) -> None:
        try:
            active.work.put_nowait(utt)
        except queue.Full:
            # STT can't keep up (e.g. CPU fallback). Audio is still on disk for the Phase 2 re-pass.
            active.dropped += 1
            self._bus.publish({"type": "warning", "code": "stt_backlog",
                               "message": "Transcriber is behind; live captions skipped a chunk."})

    def _stt_loop(self, active: _Active, stt: SpeechToText) -> None:
        while True:
            item = active.work.get()
            if item is _STOP:
                return
            utt: Utterance = item
            try:
                result = stt.transcribe(utt.samples)
            except Exception:  # noqa: BLE001 - keep the session alive
                log.exception("Transcription failed for %s %.1f-%.1f", utt.source, utt.t0, utt.t1)
                continue
            if result is None or not self._echo.accept(utt.source, utt.t0, utt.t1, result.text):
                continue
            seg = Segment(
                session_id=active.session_id, source=utt.source, t0=round(utt.t0, 2),
                t1=round(utt.t1, 2), text=result.text, language=result.language,
                avg_logprob=result.avg_logprob,
            )
            with DBSession(self._engine) as db:
                db.add(seg)
                db.commit()
                db.refresh(seg)
            self._bus.publish({"type": "segment", "session_id": active.session_id, "id": seg.id,
                               "source": seg.source, "t0": seg.t0, "t1": seg.t1,
                               "text": seg.text, "language": seg.language})

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _get_or_create_course(db: DBSession, name: str) -> Course:
        name = name.strip()[:120]
        existing = db.exec(select(Course).where(Course.name == name)).first()
        if existing:
            return existing
        course = Course(name=name)
        db.add(course)
        db.commit()
        db.refresh(course)
        return course

    def _mark(self, session_id: int, **fields) -> Session:
        with DBSession(self._engine) as db:
            row = db.get(Session, session_id)
            for key, value in fields.items():
                setattr(row, key, value)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
