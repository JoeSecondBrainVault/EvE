"""FastAPI application: REST for session control, AI pipelines, tasks + WebSocket for live captions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from eve import __version__
from eve.audio.segmenter import VoiceProbability
from eve.config import Settings, get_settings
from eve.db import make_engine
from eve.events import EventBus
from eve.models import Course, Flashcard, Note, QuizItem, Segment, Session, Task
from eve.mcp.models import MCPServerConfig
from eve.security import (
    LocalOnlyMiddleware,
    load_or_create_token,
    require_token,
    token_matches,
    websocket_origin_ok,
)
from eve.session import CaptureFactory, SessionError, SessionManager
from eve.stt.transcriber import SpeechToText

log = logging.getLogger(__name__)
WS_AUTH_TIMEOUT_S = 5.0


@dataclass
class Components:
    """Swappable hardware/model dependencies (real ones by default, fakes in tests)."""

    load_stt: Callable[[Settings], SpeechToText]
    capture_factory: Callable[[Settings], CaptureFactory]
    vad_factory: Callable[[], VoiceProbability]
    list_devices: Callable[[], list[dict[str, Any]]]
    router_factory: Callable[[Settings], Any] | None = None


def default_components() -> Components:
    def load_stt(s: Settings) -> SpeechToText:
        from eve.stt.transcriber import WhisperTranscriber

        return WhisperTranscriber(s.whisper_model, s.models_dir, device=s.whisper_device,
                                  language=s.language, initial_prompt=s.initial_prompt)

    def capture_factory(s: Settings) -> CaptureFactory:
        from eve.audio.capture import WasapiCapture

        return lambda clock: WasapiCapture(clock, loopback=s.capture_loopback, mic=s.capture_mic)

    def vad_factory() -> VoiceProbability:
        from eve.audio.vad import SileroVAD

        return SileroVAD()

    def list_devices() -> list[dict[str, Any]]:
        from eve.audio.capture import list_devices as _list

        return _list()

    def router_factory(s: Settings) -> Any:
        from eve.llm.router import LLMRouter

        return LLMRouter(s)

    return Components(load_stt, capture_factory, vad_factory, list_devices, router_factory)


# ---------------------------------------------------------------- request/response schemas
class StartSessionIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    course: str | None = Field(default=None, max_length=120)
    consent_confirmed: bool = False


class SessionOut(BaseModel):
    id: int
    session_id: int | None = None
    title: str
    course: str | None
    status: str
    started_at: Any
    ended_at: Any


class SegmentOut(BaseModel):
    id: int
    source: str
    t0: float
    t1: float
    text: str
    language: str | None


class SessionDetailOut(SessionOut):
    segments: list[SegmentOut]


class NoteOut(BaseModel):
    id: int
    session_id: int
    vault_path: str
    title: str
    summary: str
    key_takeaways: list[str]
    glossary: list[dict[str, str]]
    created_at: Any


class TaskOut(BaseModel):
    id: int
    session_id: int | None
    title: str
    due_date: Any
    status: str
    priority: str
    course_name: str | None
    evidence: str | None
    confidence: float
    created_at: Any


class TaskUpdateIn(BaseModel):
    status: str = Field(pattern="^(inbox|todo|doing|done)$")


class FlashcardOut(BaseModel):
    id: int
    session_id: int
    front: str
    back: str
    topic: str | None


class QuizItemOut(BaseModel):
    id: int
    session_id: int
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class ProcessResultOut(BaseModel):
    session_id: int
    vault_path: str
    tasks_count: int
    flashcards_count: int
    quiz_count: int


class ChatIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    course: str | None = None
    top_k: int = Field(default=4, ge=1, le=10)


class CitationOut(BaseModel):
    chunk_id: int
    session_id: int
    course_name: str | None
    session_title: str | None
    t0: float
    t1: float
    timestamp_label: str
    snippet: str


class ChatOut(BaseModel):
    answer: str
    citations: list[CitationOut]


class ChunkSearchOut(BaseModel):
    chunk_id: int
    session_id: int
    course_name: str | None
    session_title: str | None
    t0: float
    t1: float
    text: str
    score: float


class StatsOut(BaseModel):
    total_sessions: int
    total_segments: int
    total_tasks: int
    pending_tasks: int
    total_flashcards: int
    total_quizzes: int
    total_hours_recorded: float


class GoogleExchangeIn(BaseModel):
    code: str
    redirect_uri: str
    state: str | None = None


class GoogleConnectIn(BaseModel):
    app: str = Field(pattern=r"^(classroom|calendar|docs|drive|meet)$")


class GoogleClientSecretIn(BaseModel):
    content: str = Field(min_length=20, max_length=20000)



class VoiceInteractIn(BaseModel):
    input: str = Field(min_length=1, max_length=1000)
    synthesize_audio: bool = True


class VoiceInteractOut(BaseModel):
    tool: str
    arguments: dict[str, Any]
    response_text: str
    tool_output: dict[str, Any] = Field(default_factory=dict)
    audio_base64: str | None = None


class VoiceSpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = None
    speed: float | None = None


class CopilotSuggestIn(BaseModel):
    hint: str | None = None


class AssignmentAnalyzeIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=50000)
    course: str | None = None


class MeetLaunchIn(BaseModel):
    meet_url_or_code: str = Field(min_length=1, max_length=500)
    email_or_profile: str | None = None
    auto_record: bool = True
    consent_confirmed: bool = False


class AppLaunchIn(BaseModel):
    app_name: str = Field(min_length=1, max_length=100)


class MCPCallIn(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class APIKeysUpdateIn(BaseModel):
    groq_api_key: str | None = None
    gemini_api_key: str | None = None


def _mask_key(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return None
    return f"{key[:6]}••••••••{key[-4:]}"





def _session_out(row: Session, course_name: str | None) -> dict[str, Any]:
    return {"id": row.id, "session_id": row.id, "title": row.title, "course": course_name, "status": row.status,
            "started_at": row.started_at, "ended_at": row.ended_at}


# ---------------------------------------------------------------- app factory
def create_app(settings: Settings | None = None, components: Components | None = None) -> FastAPI:
    settings = settings or get_settings()
    components = components or default_components()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_dirs()
        app.state.settings = settings
        app.state.api_token = load_or_create_token(settings.data_dir)
        app.state.engine = make_engine(settings.db_path)
        app.state.bus = EventBus(asyncio.get_running_loop())
        app.state.stt = None
        app.state.model_status = "loading"

        # Initialize LLM Router
        r_fac = components.router_factory or (lambda s: None)
        app.state.router = r_fac(settings)

        # Initialize Background Reminder Scheduler
        from eve.scheduler import ReminderScheduler

        app.state.scheduler = ReminderScheduler(app.state.engine, app.state.bus)
        app.state.scheduler.start()

        # Initialize Google Classroom / Calendar periodic sync if authenticated
        try:
            from eve.integrations.google import GoogleAuthManager, GoogleIntegrationService

            g_mgr = GoogleAuthManager(settings)
            if g_mgr.get_credentials():
                g_svc = GoogleIntegrationService(app.state.engine, settings, g_mgr)
                app.state.scheduler.add_periodic_job(
                    lambda: g_svc.sync_classroom() and g_svc.sync_calendar(),
                    job_id="eve_google_sync",
                    minutes=settings.google_sync_interval_m,
                )
        except Exception as exc:  # noqa: BLE001
            log.debug("Google sync background job skipped: %s", exc)


        # Initialize Phase 5 Voice Assistant & Live Copilot
        from eve.voice.tts import TTSEngine
        from eve.voice.wakeword import WakeWordDetector
        from eve.voice.assistant import VoiceAssistant
        from eve.pipelines.copilot import LiveCopilot

        app.state.tts = TTSEngine(settings)
        app.state.wakeword = WakeWordDetector(settings, app.state.bus)
        app.state.copilot = LiveCopilot(app.state.engine, app.state.router, settings, app.state.bus)

        # Background listener linking incoming lecture speech segments to Copilot & WakeWord
        async def event_listener() -> None:
            async with app.state.bus.subscribe() as q:
                while True:
                    try:
                        evt = await q.get()
                        if evt.get("type") == "segment":
                            src = evt.get("source", "them")
                            txt = str(evt.get("text", ""))
                            t0 = float(evt.get("t0", 0.0))
                            t1 = float(evt.get("t1", 0.0))
                            app.state.copilot.add_segment(src, txt, t0, t1)
                            if src == "me":
                                app.state.wakeword.feed_text(txt)
                            if settings.copilot_enabled and app.state.copilot.should_trigger(txt):
                                asyncio.create_task(asyncio.to_thread(app.state.copilot.generate_suggestion))
                        elif evt.get("type") == "session_started":
                            if getattr(app.state, "tray", None):
                                app.state.tray.set_state("recording")
                        elif evt.get("type") == "session_stopped":
                            if getattr(app.state, "tray", None):
                                app.state.tray.set_state("idle")
                    except asyncio.CancelledError:
                        break
                    except Exception as exc:  # noqa: BLE001
                        log.debug("Event listener error: %s", exc)

        listener_task = asyncio.create_task(event_listener())

        def load_model() -> None:
            try:
                app.state.stt = components.load_stt(settings)
                app.state.model_status = "ready"
                with contextlib.suppress(RuntimeError, ValueError):
                    app.state.bus.publish({"type": "status", "model": "ready", "device": app.state.stt.device})
            except Exception as exc:  # noqa: BLE001
                log.exception("Speech model failed to load")
                app.state.model_status = "error"
                with contextlib.suppress(RuntimeError, ValueError):
                    app.state.bus.publish({"type": "status", "model": "error", "message": str(exc)[:300]})


        loader = threading.Thread(target=load_model, name="stt-loader", daemon=True)
        loader.start()
        app.state.manager = SessionManager(
            settings, app.state.engine, app.state.bus,
            stt=lambda: app.state.stt,
            capture_factory=components.capture_factory(settings),
            vad_factory=components.vad_factory,
        )
        app.state.assistant = VoiceAssistant(
            app.state.engine,
            app.state.router,
            settings,
            app.state.tts,
            app.state.manager,
        )

        # Initialize Phase 6 Retention, Rate Limiting, and Assignment Helper
        from eve.retention import SlidingWindowRateLimiter, purge_expired_recordings
        from eve.pipelines.assignments import AssignmentHelper
        from eve.tray import SystemTray

        app.state.rate_limiter = SlidingWindowRateLimiter(
            max_requests=settings.rate_limit_chat_rpm, window_seconds=60.0
        )
        app.state.assignment_helper = AssignmentHelper(
            app.state.engine, app.state.router, settings
        )

        # Register daily retention purge job
        app.state.scheduler.add_periodic_job(
            lambda: purge_expired_recordings(settings.recordings_dir, settings.retention_days),
            job_id="eve_retention_purge",
            minutes=1440,
        )

        # Optional System Tray Icon
        app.state.tray = None
        if getattr(settings, "tray_enabled", False):
            try:
                tray = SystemTray(
                    settings=settings,
                    on_start_session=lambda: app.state.manager.start(title="Tray Session", course=None, consent_confirmed=True),
                    on_stop_session=lambda: app.state.manager.stop(),
                )
                tray.run_detached()
                app.state.tray = tray
            except Exception as exc:  # noqa: BLE001
                log.debug("System tray startup skipped: %s", exc)

        # Initialize MCP Manager (Google Classroom, Gmail, Calendar, Custom Tools)
        from eve.mcp.manager import MCPManager

        app.state.mcp = MCPManager(settings)
        try:
            app.state.mcp.load_servers()
        except Exception as exc:  # noqa: BLE001
            log.debug("MCP server initial load skipped: %s", exc)

        yield
        listener_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener_task
        if getattr(app.state, "tray", None):
            app.state.tray.stop()
        if getattr(app.state, "mcp", None):
            app.state.mcp.shutdown()
        app.state.scheduler.stop()
        await asyncio.to_thread(app.state.manager.shutdown)
        app.state.engine.dispose()

    app = FastAPI(title="E.V.E. API", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)  # no public schema surface
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(LocalOnlyMiddleware, port=settings.port, origins=settings.allowed_origins)

    def get_db(request: Request) -> Iterator[DBSession]:
        with DBSession(request.app.state.engine) as db:
            yield db

    auth = [Depends(require_token)]

    def check_rate_limit(request: Request) -> None:
        limiter = getattr(request.app.state, "rate_limiter", None)
        if limiter is not None:
            client_ip = request.client.host if request.client else "127.0.0.1"
            if not limiter.is_allowed(client_ip):
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please wait a moment before sending more requests.",
                )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        origin = request.headers.get("origin")
        headers = {}
        if origin and origin in settings.allowed_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        log.exception("Unhandled server exception on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)},
            headers=headers,
        )

    @app.get("/")
    def root() -> RedirectResponse:
        from eve.app import is_service_ready
        port = 3001 if is_service_ready("http://localhost:3001") else 3000
        return RedirectResponse(url=f"http://localhost:{port}")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status", dependencies=auth)
    def status(request: Request) -> dict[str, Any]:
        st = request.app.state
        has_cloud = getattr(st.router, "has_cloud", False) if st.router else False
        dev = getattr(st.stt, "device", None) or getattr(settings, "whisper_device", "auto")
        return {"version": __version__, "model": st.model_status,
                "device": dev,
                "active_session_id": st.manager.active_session_id,
                "live_clients": st.bus.subscriber_count,
                "has_cloud_llm": has_cloud}

    @app.get("/api/devices", dependencies=auth)
    def devices() -> list[dict[str, Any]]:
        return components.list_devices()

    @app.post("/api/sessions/start", dependencies=auth, response_model=SessionOut)
    def start_session(body: StartSessionIn, request: Request, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        try:
            row = request.app.state.manager.start(title=body.title, course=body.course,
                                                  consent_confirmed=body.consent_confirmed)
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        course = db.get(Course, row.course_id) if row.course_id else None
        return _session_out(row, course.name if course else None)

    @app.post("/api/sessions/stop", dependencies=auth, response_model=SessionOut)
    def stop_session(request: Request, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        try:
            row = request.app.state.manager.stop()
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        course = db.get(Course, row.course_id) if row.course_id else None
        return _session_out(row, course.name if course else None)

    @app.get("/api/sessions", dependencies=auth, response_model=list[SessionOut])
    def list_sessions(db: DBSession = Depends(get_db), limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        rows = db.exec(
            select(Session, Course).join(Course, isouter=True)
            .where(Session.status != "failed")
            .order_by(col(Session.started_at).desc()).limit(limit)
        ).all()
        return [_session_out(s, c.name if c else None) for s, c in rows]

    @app.get("/api/sessions/{session_id}", dependencies=auth, response_model=SessionDetailOut)
    def get_session(session_id: int, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        row = db.get(Session, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        course = db.get(Course, row.course_id) if row.course_id else None
        segs = db.exec(select(Segment).where(Segment.session_id == session_id)
                       .order_by(col(Segment.t0))).all()
        out = _session_out(row, course.name if course else None)
        out["segments"] = [SegmentOut.model_validate(s, from_attributes=True).model_dump() for s in segs]
        return out

    # ---------------------------------------------------------------- Phase 2: Post-session & Intelligence
    @app.post("/api/sessions/{session_id}/process", dependencies=auth, response_model=ProcessResultOut)
    def process_session(session_id: int, request: Request, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        session = db.get(Session, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        from eve.pipelines.lecture import process_session_pipeline

        try:
            note_path = process_session_pipeline(
                session_id=session_id,
                engine=request.app.state.engine,
                settings=request.app.state.settings,
                router=request.app.state.router,
                bus=request.app.state.bus,
            )
        except Exception as exc:
            log.exception("Session processing failed for #%d", session_id)
            raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc

        tasks_count = len(db.exec(select(Task).where(Task.session_id == session_id)).all())
        flashcards_count = len(db.exec(select(Flashcard).where(Flashcard.session_id == session_id)).all())
        quiz_count = len(db.exec(select(QuizItem).where(QuizItem.session_id == session_id)).all())

        return {
            "session_id": session_id,
            "vault_path": str(note_path),
            "tasks_count": tasks_count,
            "flashcards_count": flashcards_count,
            "quiz_count": quiz_count,
        }

    @app.get("/api/sessions/{session_id}/note", dependencies=auth, response_model=NoteOut)
    def get_session_note(session_id: int, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        note = db.exec(select(Note).where(Note.session_id == session_id)).first()
        if not note:
            raise HTTPException(status_code=404, detail="No note generated for this session yet")
        return {
            "id": note.id,
            "session_id": note.session_id,
            "vault_path": note.vault_path,
            "title": note.title,
            "summary": note.summary,
            "key_takeaways": json.loads(note.key_points_json),
            "glossary": json.loads(note.glossary_json),
            "created_at": note.created_at,
        }

    @app.get("/api/sessions/{session_id}/flashcards", dependencies=auth, response_model=list[FlashcardOut])
    def get_session_flashcards(session_id: int, db: DBSession = Depends(get_db)) -> list[dict[str, Any]]:
        rows = db.exec(select(Flashcard).where(Flashcard.session_id == session_id)).all()
        return [FlashcardOut.model_validate(r, from_attributes=True).model_dump() for r in rows]

    @app.get("/api/sessions/{session_id}/quiz", dependencies=auth, response_model=list[QuizItemOut])
    def get_session_quiz(session_id: int, db: DBSession = Depends(get_db)) -> list[dict[str, Any]]:
        rows = db.exec(select(QuizItem).where(QuizItem.session_id == session_id)).all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "session_id": r.session_id,
                "question": r.question,
                "options": json.loads(r.options_json),
                "correct_index": r.correct_index,
                "explanation": r.explanation,
            })
        return out

    # ---------------------------------------------------------------- Phase 2: Tasks & Deadlines
    @app.get("/api/tasks", dependencies=auth, response_model=list[TaskOut])
    def list_tasks(
        status: str | None = None,
        course: str | None = None,
        db: DBSession = Depends(get_db),
    ) -> list[dict[str, Any]]:
        query = select(Task)
        if status:
            query = query.where(Task.status == status)
        if course:
            query = query.where(Task.course_name == course)
        rows = db.exec(query.order_by(col(Task.due_date).asc(), col(Task.created_at).desc())).all()
        return [TaskOut.model_validate(r, from_attributes=True).model_dump() for r in rows]

    @app.post("/api/tasks/{task_id}/status", dependencies=auth, response_model=TaskOut)
    def update_task_status(task_id: int, body: TaskUpdateIn, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        task.status = body.status
        db.add(task)
        db.commit()
        db.refresh(task)
        return TaskOut.model_validate(task, from_attributes=True).model_dump()

    # ---------------------------------------------------------------- Phase 3: RAG Chat & Search
    @app.post("/api/chat", dependencies=auth, response_model=ChatOut)
    def rag_chat(body: ChatIn, request: Request, db: DBSession = Depends(get_db)) -> dict[str, Any]:
        check_rate_limit(request)
        from eve.rag.embeddings import EmbeddingEngine
        from eve.rag.chat import HybridRAGSearcher

        emb_engine = EmbeddingEngine(settings)
        searcher = HybridRAGSearcher(request.app.state.engine, emb_engine)
        ans = searcher.answer_question(body.query, course_filter=body.course, router=request.app.state.router, top_k=body.top_k)
        return ans.model_dump()

    @app.get("/api/chat/search", dependencies=auth, response_model=list[ChunkSearchOut])
    def rag_search(
        request: Request,
        q: str = Query(min_length=1),
        course: str | None = None,
        top_k: int = Query(default=5, ge=1, le=50),
    ) -> list[dict[str, Any]]:
        from eve.rag.embeddings import EmbeddingEngine
        from eve.rag.chat import HybridRAGSearcher

        emb_engine = EmbeddingEngine(settings)
        searcher = HybridRAGSearcher(request.app.state.engine, emb_engine)
        chunks = searcher.search(q, course_filter=course, top_k=top_k)
        return [c.model_dump() for c in chunks]

    @app.post("/api/sessions/{session_id}/index", dependencies=auth)
    def index_session(session_id: int, request: Request) -> dict[str, Any]:
        from eve.rag.embeddings import EmbeddingEngine
        from eve.rag.index import index_session_chunks

        emb_engine = EmbeddingEngine(settings)
        count = index_session_chunks(session_id, request.app.state.engine, emb_engine)
        return {"status": "ok", "session_id": session_id, "chunks_indexed": count}

    @app.get("/api/sessions/{session_id}/audio/{source}", dependencies=auth)
    def stream_session_audio(session_id: int, source: str, db: DBSession = Depends(get_db)) -> FileResponse:
        if source not in ("them", "me"):
            raise HTTPException(status_code=400, detail="Source must be 'them' or 'me'")
        session_row = db.get(Session, session_id)
        rec_dir: Path | None = None
        if session_row and session_row.recording_dir:
            p = Path(session_row.recording_dir)
            if p.exists() and p.is_dir():
                rec_dir = p
        if rec_dir is None:
            import re
            pattern = re.compile(rf"^\d{{8}}-\d{{6}}-{session_id}-")
            if settings.recordings_dir.exists():
                for d in settings.recordings_dir.iterdir():
                    if d.is_dir() and pattern.match(d.name):
                        rec_dir = d
                        break
        if rec_dir is None:
            raise HTTPException(status_code=404, detail=f"Recording for session #{session_id} not found")
        wav_file = rec_dir / f"{source}.wav"
        if not wav_file.exists():
            raise HTTPException(status_code=404, detail=f"Audio file {source}.wav not found for session #{session_id}")
        return FileResponse(wav_file, media_type="audio/wav")

    # ---------------------------------------------------------------- Dashboard Stats
    @app.get("/api/stats", dependencies=auth, response_model=StatsOut)
    def get_stats(db: DBSession = Depends(get_db)) -> dict[str, Any]:
        from sqlmodel import func

        total_sessions = db.exec(select(func.count(Session.id)).where(Session.status != "failed")).one() or 0
        total_segments = db.exec(select(func.count(Segment.id))).one() or 0
        total_tasks = db.exec(select(func.count(Task.id))).one() or 0
        pending_tasks = db.exec(select(func.count(Task.id)).where(Task.status.in_(["inbox", "todo"]))).one() or 0
        total_flashcards = db.exec(select(func.count(Flashcard.id))).one() or 0
        total_quizzes = db.exec(select(func.count(QuizItem.id))).one() or 0

        total_seconds = db.exec(select(func.sum(Segment.t1 - Segment.t0))).one() or 0.0
        hours = round(float(total_seconds) / 3600.0, 2)

        return {
            "total_sessions": total_sessions,
            "total_segments": total_segments,
            "total_tasks": total_tasks,
            "pending_tasks": pending_tasks,
            "total_flashcards": total_flashcards,
            "total_quizzes": total_quizzes,
            "total_hours_recorded": hours,
        }

    # ---------------------------------------------------------------- Phase 4: Google Classroom & Calendar
    @app.get("/api/integrations/google/status", dependencies=auth)
    def google_status() -> dict[str, Any]:
        from eve.integrations.google import GoogleAuthManager

        mgr = GoogleAuthManager(settings)
        configured = mgr.has_credentials_configured()
        authenticated = mgr.get_credentials() is not None
        return {
            "configured": configured,
            "authenticated": authenticated,
            "calendar_name": settings.google_calendar_name,
        }

    # Pending OAuth logins: state -> PKCE verifier + requested scopes (expires after 10 minutes).
    oauth_pending: dict[str, dict[str, Any]] = {}
    granted_cache: dict[str, Any] = {"token": None, "info": None}
    google_redirect = f"http://127.0.0.1:{settings.port}/api/integrations/google/callback"

    def _begin_google_flow(scopes: list[str], redirect_uri: str = google_redirect) -> tuple[str, str]:
        import secrets
        import time

        from eve.integrations.google import IDENTITY_SCOPES, GoogleAuthManager

        mgr = GoogleAuthManager(settings)
        requested = list(dict.fromkeys(IDENTITY_SCOPES + scopes))
        try:
            flow = mgr.get_flow(redirect_uri, scopes=requested)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state = secrets.token_urlsafe(32)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        now = time.monotonic()
        for stale in [k for k, v in oauth_pending.items() if now - v["created"] > 600]:
            oauth_pending.pop(stale, None)
        oauth_pending[state] = {
            "verifier": flow.code_verifier,
            "scopes": requested,
            "redirect_uri": redirect_uri,
            "created": now,
        }
        return auth_url, state

    def _granted(mgr: Any, creds: Any) -> dict[str, Any]:
        if granted_cache["token"] != creds.token or granted_cache["info"] is None:
            granted_cache["info"] = mgr.granted_info(creds)
            granted_cache["token"] = creds.token
        return granted_cache["info"]

    @app.get("/api/integrations/google/auth-url", dependencies=auth)
    def google_auth_url(redirect_uri: str = google_redirect) -> dict[str, str]:
        from eve.integrations.google import SCOPES

        if redirect_uri != google_redirect:
            raise HTTPException(status_code=400, detail="Only the local E.V.E. callback redirect URI is allowed.")
        auth_url, state = _begin_google_flow(SCOPES, redirect_uri)
        return {"auth_url": auth_url, "state": state}

    @app.get("/api/integrations/google/apps", dependencies=auth)
    def google_apps() -> dict[str, Any]:
        """Real connection state per classroom app, based on scopes Google actually granted."""
        from eve.integrations.google import APP_SCOPES, GoogleAuthManager

        mgr = GoogleAuthManager(settings)
        configured = mgr.has_credentials_configured()
        creds = mgr.get_credentials() if configured else None
        info = _granted(mgr, creds) if creds else {"scopes": [], "email": None}
        granted = set(info["scopes"])
        apps = {
            name: {"connected": creds is not None and all(s in granted for s in scopes), "scopes": scopes}
            for name, scopes in APP_SCOPES.items()
        }
        return {
            "configured": configured,
            "authenticated": creds is not None,
            "email": info.get("email"),
            "apps": apps,
        }

    @app.post("/api/integrations/google/connect", dependencies=auth)
    def google_connect(body: GoogleConnectIn, request: Request) -> dict[str, str]:
        """Start Google sign-in + permission consent for one app in the system browser.

        Google blocks sign-in inside embedded webviews, so the consent page is opened in the
        user's real default browser; the dashboard polls /apps until the grant lands.
        """
        import webbrowser

        from eve.integrations.google import APP_SCOPES

        check_rate_limit(request)
        auth_url, _ = _begin_google_flow(APP_SCOPES[body.app])
        opened = False
        try:
            opened = webbrowser.open(auth_url, new=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not open system browser for Google sign-in: %s", exc)
        return {"auth_url": auth_url, "opened": "true" if opened else "false"}

    @app.post("/api/integrations/google/apps/{app_name}/action", dependencies=auth)
    def google_app_action(app_name: str, request: Request) -> dict[str, Any]:
        """Run the app's real Google API action to prove the connection works."""
        from eve.integrations.google import APP_SCOPES, GoogleAuthManager, GoogleIntegrationService

        check_rate_limit(request)
        if app_name not in APP_SCOPES:
            raise HTTPException(status_code=404, detail="Unknown Google app.")
        mgr = GoogleAuthManager(settings)
        creds = mgr.get_credentials()
        if not creds:
            raise HTTPException(status_code=401, detail="Google account not connected.")
        granted = set(_granted(mgr, creds)["scopes"])
        if not all(s in granted for s in APP_SCOPES[app_name]):
            raise HTTPException(status_code=403, detail=f"Permission for {app_name} has not been granted yet.")

        service = GoogleIntegrationService(request.app.state.engine, settings, mgr)
        if app_name == "classroom":
            return service.sync_classroom(creds)
        if app_name == "calendar":
            return service.sync_calendar(creds)
        if app_name == "docs":
            return service.list_recent_docs(creds)
        if app_name == "drive":
            return service.list_recent_drive_files(creds)
        return service.create_meet_space(creds)

    @app.post("/api/integrations/google/client-secret", dependencies=auth)
    def google_client_secret(body: GoogleClientSecretIn, request: Request) -> dict[str, str]:
        """Save the OAuth client JSON downloaded from Google Cloud Console (Desktop app type)."""
        check_rate_limit(request)
        try:
            data = json.loads(body.content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="That is not valid JSON.") from exc
        info = data.get("installed") if isinstance(data, dict) else None
        if not isinstance(info, dict):
            raise HTTPException(
                status_code=400,
                detail="Expected a 'Desktop app' OAuth client JSON (top-level key 'installed').",
            )
        cid, csec = info.get("client_id"), info.get("client_secret")
        if not (isinstance(cid, str) and cid.endswith(".apps.googleusercontent.com") and isinstance(csec, str) and csec):
            raise HTTPException(status_code=400, detail="client_id / client_secret missing or malformed.")
        target = settings.google_client_secrets_file or (settings.data_dir / "client_secret.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding="utf-8")
        return {"status": "ok", "message": "Google OAuth client saved. You can now connect your apps."}

    @app.post("/api/integrations/google/exchange", dependencies=auth)
    def google_exchange(body: GoogleExchangeIn) -> dict[str, Any]:
        from eve.integrations.google import GoogleAuthManager, save_refresh_token

        match_key = None
        if body.state and body.state in oauth_pending:
            match_key = body.state
        else:
            for k, v in sorted(oauth_pending.items(), key=lambda item: item[1]["created"], reverse=True):
                if v["redirect_uri"] == body.redirect_uri:
                    match_key = k
                    break
        if match_key is None:
            raise HTTPException(status_code=400, detail="No pending Google sign-in for this redirect URI or expired state.")
        pending = oauth_pending.pop(match_key)
        mgr = GoogleAuthManager(settings)
        try:
            flow = mgr.get_flow(body.redirect_uri, scopes=pending["scopes"], code_verifier=pending["verifier"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            flow.fetch_token(code=body.code)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to fetch token from Google: {exc}") from exc
        creds = flow.credentials
        if not creds.refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token returned by Google OAuth. Ensure prompt='consent' was used.")
        save_refresh_token(creds.refresh_token)
        return {"status": "ok", "message": "Google account authenticated and refresh token saved to Windows Credential Manager."}

    @app.post("/api/integrations/google/sync", dependencies=auth)
    def google_sync(request: Request, target: str = "all") -> dict[str, Any]:
        from eve.integrations.google import GoogleAuthManager, GoogleIntegrationService

        mgr = GoogleAuthManager(settings)
        creds = mgr.get_credentials()
        if not creds:
            raise HTTPException(status_code=401, detail="Google account not authenticated.")

        service = GoogleIntegrationService(request.app.state.engine, settings, mgr)
        results: dict[str, Any] = {}

        if target in ("all", "classroom"):
            results["classroom"] = service.sync_classroom(creds)
        if target in ("all", "calendar"):
            results["calendar"] = service.sync_calendar(creds)

        return {"status": "ok", "results": results}

    @app.post("/api/integrations/google/disconnect", dependencies=auth)
    def google_disconnect() -> dict[str, str]:
        from eve.integrations.google import GoogleAuthManager

        GoogleAuthManager(settings).revoke()
        granted_cache.update(token=None, info=None)
        return {"status": "ok", "message": "Google access revoked and token cleared from Windows Credential Manager."}

    def _oauth_page(title: str, message: str, ok: bool) -> HTMLResponse:
        import html

        color = "#34d399" if ok else "#fb7185"
        body = (
            "<!doctype html><html><head><meta charset='utf-8'><title>E.V.E. - Google</title></head>"
            "<body style='background:#020617;color:#e2e8f0;font-family:system-ui;display:flex;"
            "align-items:center;justify-content:center;height:100vh;margin:0'>"
            "<div style='max-width:460px;text-align:center;padding:32px;border:1px solid #1e293b;"
            "border-radius:16px;background:#0f172a'>"
            f"<h1 style='color:{color};font-size:22px'>{html.escape(title)}</h1>"
            f"<p style='color:#94a3b8;font-size:14px;line-height:1.6'>{html.escape(message)}</p>"
            "</div></body></html>"
        )
        return HTMLResponse(content=body, status_code=200 if ok else 400)

    @app.get("/api/integrations/google/callback")
    def google_callback(
        request: Request,
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
    ) -> Response:
        import sys

        from eve.integrations.google import GoogleAuthManager, save_refresh_token

        pending = oauth_pending.pop(state, None) if state else None
        if error:
            return _oauth_page("Permission not granted", f"Google returned: {error}. You can close this tab.", ok=False)
        if pending is None or not code:
            log.warning("Google OAuth callback with unknown/expired state")
            return _oauth_page(
                "Sign-in link expired",
                "This sign-in request is unknown or expired. Return to E.V.E. and click Connect again.",
                ok=False,
            )

        mgr = GoogleAuthManager(settings)
        try:
            flow = mgr.get_flow(pending["redirect_uri"], scopes=pending["scopes"], code_verifier=pending["verifier"])
            flow.fetch_token(code=code)
        except Exception as exc:  # noqa: BLE001
            log.warning("Google OAuth code exchange failed: %s", exc)
            return _oauth_page("Connection failed", "Google rejected the sign-in. Please try Connect again.", ok=False)

        creds = flow.credentials
        if not creds.refresh_token:
            return _oauth_page("Connection failed", "Google did not return a refresh token. Please try again.", ok=False)
        save_refresh_token(creds.refresh_token)
        granted_cache.update(token=None, info=None)

        ws_cfg = MCPServerConfig(
            name="google_workspace",
            command=sys.executable,
            args=["-m", "eve.mcp.servers.workspace"],
            enabled=True,
            description="Google Classroom, Calendar MCP tools",
        )
        with contextlib.suppress(Exception):
            request.app.state.mcp.save_server(ws_cfg)
        return _oauth_page(
            "Connected to E.V.E.",
            "Permission granted. You can close this tab and return to E.V.E. - your app now shows as Connected.",
            ok=True,
        )

    # ---------------------------------------------------------------- Settings & API Keys Management
    @app.get("/api/settings/keys", dependencies=auth)
    def get_api_keys(request: Request) -> dict[str, Any]:
        gemini_key = settings.resolved_gemini_api_key
        groq_key = settings.resolved_groq_api_key
        router = request.app.state.router
        active_provider = "ollama"
        if getattr(router, "_groq_client", None) is not None:
            active_provider = "groq"
        elif getattr(router, "_gemini_client", None) is not None:
            active_provider = "gemini"

        return {
            "gemini": {
                "configured": bool(gemini_key),
                "masked": _mask_key(gemini_key),
                "model": settings.gemini_model,
            },
            "groq": {
                "configured": bool(groq_key),
                "masked": _mask_key(groq_key),
                "model": settings.groq_model,
            },
            "active_provider": active_provider,
            "has_cloud": router.has_cloud if router else False,
        }

    @app.post("/api/settings/keys", dependencies=auth)
    def update_api_keys(body: APIKeysUpdateIn, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        import os
        import dotenv
        from eve.config import PROJECT_ROOT

        env_path = PROJECT_ROOT / ".env"
        if not env_path.exists():
            env_path.touch()

        updated_items = []

        if body.groq_api_key is not None:
            val = body.groq_api_key.strip()
            if val:
                dotenv.set_key(str(env_path), "GROQ_API_KEY", val)
                dotenv.set_key(str(env_path), "EVE_GROQ_API_KEY", val)
                os.environ["GROQ_API_KEY"] = val
                os.environ["EVE_GROQ_API_KEY"] = val
                settings.groq_api_key = val
                updated_items.append("Groq")

        if body.gemini_api_key is not None:
            val = body.gemini_api_key.strip()
            if val:
                dotenv.set_key(str(env_path), "GEMINI_API_KEY", val)
                dotenv.set_key(str(env_path), "EVE_GEMINI_API_KEY", val)
                os.environ["GEMINI_API_KEY"] = val
                os.environ["EVE_GEMINI_API_KEY"] = val
                settings.gemini_api_key = val
                updated_items.append("Gemini")

        if request.app.state.router:
            request.app.state.router.reload_clients()

        return {
            "status": "ok",
            "message": f"Updated and activated: {', '.join(updated_items) if updated_items else 'No changes'}",
            "groq_configured": bool(settings.resolved_groq_api_key),
            "gemini_configured": bool(settings.resolved_gemini_api_key),
        }

    # ---------------------------------------------------------------- Phase 5: Voice Assistant & Live Copilot

    @app.get("/api/voice/status", dependencies=auth)
    def voice_status(request: Request) -> dict[str, Any]:
        st = request.app.state
        return {
            "wakeword_enabled": settings.wakeword_enabled,
            "wakeword_loaded": st.wakeword.has_onnx_model,
            "tts_enabled": settings.tts_enabled,
            "tts_loaded": st.tts.is_available,
            "tts_voice": settings.tts_voice,
            "tts_speed": settings.tts_speed,
            "copilot_enabled": settings.copilot_enabled,
        }

    @app.post("/api/voice/interact", dependencies=auth, response_model=VoiceInteractOut)
    def voice_interact(body: VoiceInteractIn, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        resp = request.app.state.assistant.process_command(body.input, synthesize_audio=body.synthesize_audio)
        return resp.model_dump()

    @app.post("/api/voice/speak", dependencies=auth)
    def voice_speak(body: VoiceSpeakIn, request: Request) -> Response:
        wav_bytes = request.app.state.tts.synthesize_wav_bytes(body.text, voice=body.voice, speed=body.speed)
        return Response(content=wav_bytes, media_type="audio/wav")

    @app.post("/api/voice/wakeword/trigger", dependencies=auth)
    def wakeword_trigger(request: Request) -> dict[str, str]:
        request.app.state.wakeword.trigger(trigger_source="api")
        return {"status": "ok", "message": "Wake word triggered successfully."}

    @app.get("/api/copilot/recent", dependencies=auth)
    def copilot_recent(request: Request) -> dict[str, Any]:
        last = request.app.state.copilot.last_suggestion
        return {
            "suggestion": last.model_dump() if last else None,
            "window_text": request.app.state.copilot.get_window_text(),
        }

    @app.post("/api/copilot/suggest", dependencies=auth)
    def copilot_suggest(body: CopilotSuggestIn, request: Request) -> dict[str, Any]:
        suggestion = request.app.state.copilot.generate_suggestion(body.hint)
        return {
            "status": "ok",
            "suggestion": suggestion.model_dump() if suggestion else None,
        }

    # ---------------------------------------------------------------- Phase 6: Assignment Helper & Hardening
    @app.post("/api/assignments/analyze", dependencies=auth)
    def analyze_assignment(body: AssignmentAnalyzeIn, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        try:
            analysis = request.app.state.assignment_helper.analyze_assignment(
                body.prompt, course_filter=body.course
            )
            return analysis.model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("Assignment analysis failed")
            raise HTTPException(status_code=500, detail=f"Assignment analysis failed: {exc}") from exc

    @app.post("/api/assignments/upload", dependencies=auth)
    async def upload_assignment(
        request: Request,
        file: UploadFile = File(...),
        course: str | None = Form(default=None),
    ) -> dict[str, Any]:
        check_rate_limit(request)
        filename = file.filename or "assignment.txt"
        lower_name = filename.lower()
        if not lower_name.endswith((".pdf", ".docx", ".txt", ".md")):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload a .pdf, .docx, .txt, or .md file.",
            )

        content = await file.read()
        if len(content) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {settings.max_upload_size_bytes // (1024 * 1024)}MB.",
            )

        try:
            from eve.pipelines.assignments import extract_text_from_file_bytes

            extracted_text = extract_text_from_file_bytes(filename, content)
            if not extracted_text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Uploaded file contains no readable text content.",
                )
            analysis = request.app.state.assignment_helper.analyze_assignment(
                extracted_text, course_filter=course
            )
            return analysis.model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("Assignment document processing failed")
            raise HTTPException(status_code=500, detail=f"Document analysis failed: {exc}") from exc

    @app.post("/api/retention/purge", dependencies=auth)
    def trigger_retention_purge(request: Request) -> dict[str, Any]:
        from eve.retention import purge_expired_recordings

        purged_count, freed_bytes = purge_expired_recordings(
            settings.recordings_dir, retention_days=settings.retention_days
        )
        return {
            "status": "ok",
            "purged_count": purged_count,
            "freed_bytes": freed_bytes,
            "retention_days": settings.retention_days,
        }

    # ---------------------------------------------------------------- Desktop, Google Meet, & MCP Integrations
    @app.get("/api/integrations/chrome/profiles", dependencies=auth)
    def get_chrome_profiles() -> dict[str, Any]:
        from eve.integrations.chrome import list_chrome_profiles

        profiles = list_chrome_profiles()
        return {"profiles": profiles}

    @app.post("/api/integrations/meet/launch", dependencies=auth)
    def launch_meet(body: MeetLaunchIn, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        from eve.integrations.chrome import launch_meet_in_chrome

        res = launch_meet_in_chrome(body.meet_url_or_code, body.email_or_profile)
        if body.auto_record and request.app.state.manager:
            if not body.consent_confirmed:
                res["recording"] = False
                res["recording_error"] = "Recording requires confirming that participants are informed."
            else:
                try:
                    session = request.app.state.manager.start(
                        title=f"Google Meet ({res.get('email', 'Class')})",
                        course=None,
                        consent_confirmed=True,
                    )
                    res["session_id"] = session.id
                    res["recording"] = True
                except Exception as exc:
                    log.warning("Auto-recording Google Meet session failed: %s", exc)
                    res["recording_error"] = str(exc)
        return res

    @app.post("/api/integrations/apps/launch", dependencies=auth)
    def launch_desktop_app(body: AppLaunchIn, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        return request.app.state.assistant._tool_open_computer_app({"app_name": body.app_name})

    @app.get("/api/mcp/servers", dependencies=auth)
    def list_mcp_servers(request: Request) -> dict[str, Any]:
        servers = request.app.state.mcp.list_servers()
        return {"servers": servers}

    @app.post("/api/mcp/servers", dependencies=auth)
    def save_mcp_server(body: MCPServerConfig, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        import shutil
        import sys
        from pathlib import Path

        # 1. Strictly validate command executable
        cmd_str = body.command.strip()
        cmd_path = Path(cmd_str)
        is_allowed_cmd = False

        if len(cmd_path.parts) > 1 or cmd_path.is_absolute():
            try:
                resolved_cmd = cmd_path.resolve()
                venv_prefix = Path(sys.prefix).resolve()
                sys_exe = Path(sys.executable).resolve()
                if resolved_cmd == sys_exe or resolved_cmd.is_relative_to(venv_prefix):
                    is_allowed_cmd = True
            except Exception:
                is_allowed_cmd = False
        else:
            base_name = cmd_str.lower()
            if base_name in ("python", "python3", "python.exe"):
                is_allowed_cmd = True
                body.command = sys.executable
            elif base_name in ("node", "node.exe"):
                is_allowed_cmd = shutil.which(cmd_str) is not None
            elif base_name in ("uv", "uv.exe"):
                is_allowed_cmd = shutil.which(cmd_str) is not None

        if not is_allowed_cmd:
            raise HTTPException(
                status_code=400,
                detail=f"Disallowed command runtime: '{body.command}'. Only the current Python virtualenv or validated runtimes are permitted.",
            )

        # 2. Strictly validate arguments to prevent arbitrary code execution
        dangerous_flags = {
            "-c", "--command", "-e", "--eval", "/c", "/k", "-r", "--require",
            "--input-type", "-i", "--interactive",
        }
        disallowed_chars = {";", "&", "|", "<", ">", "`", "$", "\n", "\r"}

        for arg in body.args:
            arg_clean = arg.strip()
            if arg_clean.lower() in dangerous_flags:
                raise HTTPException(
                    status_code=400,
                    detail=f"Disallowed execution argument: '{arg}'. Inline code evaluation flags are prohibited.",
                )
            if any(ch in arg_clean for ch in disallowed_chars):
                raise HTTPException(
                    status_code=400,
                    detail="Command arguments cannot contain shell metacharacters (; & | < > ` $).",
                )

        if body.args and body.args[0] == "-m":
            if len(body.args) < 2 or not body.args[1].startswith("eve.mcp.servers."):
                raise HTTPException(
                    status_code=400,
                    detail="Python MCP servers launched with '-m' must target approved modules in 'eve.mcp.servers.*'.",
                )

        success = request.app.state.mcp.save_server(body)
        if not success and body.enabled:
            return {"status": "error", "message": "Failed to connect to MCP server stdio process."}
        return {"status": "ok" if success else "error"}

    @app.get("/api/mcp/tools", dependencies=auth)
    def list_mcp_tools(request: Request) -> dict[str, Any]:
        tools = [t.model_dump() for t in request.app.state.mcp.list_all_tools()]
        return {"tools": tools}

    @app.post("/api/mcp/call", dependencies=auth)
    def call_mcp_tool(body: MCPCallIn, request: Request) -> dict[str, Any]:
        check_rate_limit(request)
        result = request.app.state.mcp.call_tool(body.tool_name, body.arguments)
        return result.model_dump()

    # ---------------------------------------------------------------- WebSocket

    @app.websocket("/ws/live")
    async def live(ws: WebSocket) -> None:
        st = ws.app.state
        if not websocket_origin_ok(ws.headers.get("origin"), settings.port, settings.allowed_origins):
            await ws.close(code=4403)
            return
        await ws.accept()
        # Browsers cannot set Authorization on WebSockets and query strings end up in logs,
        # so the token is sent as the first message instead.
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=WS_AUTH_TIMEOUT_S)
            msg = json.loads(raw)
        except (TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
            await _safe_close(ws, 4401)
            return
        if not (isinstance(msg, dict) and msg.get("type") == "auth"
                and token_matches(st.api_token, str(msg.get("token", "")))):
            await _safe_close(ws, 4401)
            return
        async with st.bus.subscribe() as queue:
            await ws.send_json({"type": "hello", "model": st.model_status,
                                "active_session_id": st.manager.active_session_id})
            receiver = asyncio.create_task(_drain_client(ws))
            try:
                while not receiver.done():
                    getter = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                    if getter in done:
                        await ws.send_json(getter.result())
                    else:
                        getter.cancel()
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                receiver.cancel()

    return app


async def _drain_client(ws: WebSocket) -> None:
    """Consume (and ignore) client messages so disconnects are detected promptly."""
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await ws.receive_text()


async def _safe_close(ws: WebSocket, code: int) -> None:
    with contextlib.suppress(RuntimeError):
        await ws.close(code=code)
