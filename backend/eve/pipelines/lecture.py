"""Complete post-session processing pipeline: analysis, task extraction, and Obsidian publishing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from eve.config import Settings
from eve.events import EventBus
from eve.integrations.obsidian import ObsidianPublisher, format_seconds
from eve.llm.prompts import (
    LECTURE_SYSTEM_PROMPT,
    LECTURE_USER_PROMPT,
    LectureAnalysis,
    RawExtractedTask,
)
from eve.llm.router import LLMRouter
from eve.models import Course, Flashcard, Note, QuizItem, Segment, Session, Task
from eve.pipelines.tasks import extract_tasks_from_transcript, parse_relative_deadline

log = logging.getLogger(__name__)


def process_session_pipeline(
    session_id: int,
    engine: Engine,
    settings: Settings,
    router: LLMRouter,
    bus: EventBus,
) -> Path:
    """Run post-session intelligence pass, write to Obsidian, and record tasks/flashcards."""
    with DBSession(engine) as db:
        session = db.get(Session, session_id)
        if session is None:
            raise ValueError(f"Session #{session_id} not found")

        course = db.get(Course, session.course_id) if session.course_id else None
        course_name = course.name if course else None

        segments = db.exec(
            select(Segment)
            .where(Segment.session_id == session_id)
            .order_by(col(Segment.t0))
        ).all()

    if not segments:
        log.warning("Session #%d has no transcribed segments to process", session_id)
        # Create minimal fallback note
        analysis = LectureAnalysis(
            title=session.title,
            summary="No speech or dialogue was captured during this session.",
            key_takeaways=["No recorded audio content."],
            glossary=[],
            flashcards=[],
            quiz=[],
        )
        tasks: list[RawExtractedTask] = []
    else:
        # Build formatted transcript
        transcript_lines = []
        for s in segments:
            speaker = "Instructor / Speaker" if s.source == "them" else "Student / You"
            ts = f"[{format_seconds(s.t0)}]"
            transcript_lines.append(f"{ts} {speaker}: {s.text}")
        full_transcript = "\n".join(transcript_lines)

        date_str = session.started_at.strftime("%Y-%m-%d %A %H:%M")
        user_prompt = LECTURE_USER_PROMPT.format(
            course=course_name or "General",
            title=session.title,
            date=date_str,
            transcript=full_transcript,
        )

        # 1. Synthesize comprehensive lecture analysis
        analysis, provider = router.generate_structured(
            user_prompt,
            system_prompt=LECTURE_SYSTEM_PROMPT,
            schema=LectureAnalysis,
        )
        log.info("Session #%d analyzed with %s: '%s'", session_id, provider, analysis.title)

        # 2. Extract coursework deadlines & tasks
        tasks = extract_tasks_from_transcript(router, full_transcript, course_name, session.started_at)

    # 3. Publish directly to Obsidian Second Brain
    publisher = ObsidianPublisher(settings)
    note_path = publisher.publish_lecture_note(session, course_name, analysis, tasks, segments)

    # 4. Save metadata, tasks, flashcards, and quiz items into database
    with DBSession(engine) as db:
        # Save or update Note record
        existing_note = db.exec(select(Note).where(Note.session_id == session_id)).first()
        if existing_note:
            db.delete(existing_note)
            db.commit()

        note_row = Note(
            session_id=session_id,
            vault_path=str(note_path),
            title=analysis.title,
            summary=analysis.summary,
            key_points_json=json.dumps(analysis.key_takeaways),
            glossary_json=json.dumps([{"term": g.term, "definition": g.definition} for g in analysis.glossary]),
        )
        db.add(note_row)

        # Save Tasks
        for t in tasks:
            due_dt = parse_relative_deadline(t.due_phrase, session.started_at)
            # Route low confidence or unverified deadlines to 'inbox' for manual confirmation
            initial_status = "todo" if (t.confidence >= 0.7 and due_dt is not None) else "inbox"
            task_row = Task(
                session_id=session_id,
                title=t.title,
                due_date=due_dt,
                status=initial_status,
                priority=t.priority,
                course_name=course_name,
                evidence=t.evidence,
                confidence=t.confidence,
            )
            db.add(task_row)

        # Save Flashcards
        for fc in analysis.flashcards:
            fc_row = Flashcard(
                session_id=session_id,
                front=fc.front,
                back=fc.back,
                topic=fc.topic,
            )
            db.add(fc_row)

        # Save Quiz Items
        for q in analysis.quiz:
            q_row = QuizItem(
                session_id=session_id,
                question=q.question,
                options_json=json.dumps(q.options),
                correct_index=q.correct_index,
                explanation=q.explanation,
            )
            db.add(q_row)

        # Mark session as processed
        db_session = db.get(Session, session_id)
        if db_session:
            db_session.status = "processed"
            db.add(db_session)

        db.commit()

    # 5. Index chunks for hybrid RAG search
    try:
        from eve.rag.embeddings import EmbeddingEngine
        from eve.rag.index import index_session_chunks

        emb_engine = EmbeddingEngine(settings)
        indexed_chunks = index_session_chunks(session_id, engine, emb_engine)
        log.info("Session #%d indexed %d chunks for RAG", session_id, indexed_chunks)
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG chunk indexing for session #%d failed: %s", session_id, exc)

    bus.publish({
        "type": "lecture_processed",
        "session_id": session_id,
        "title": analysis.title,
        "vault_path": str(note_path),
        "tasks_count": len(tasks),
        "flashcards_count": len(analysis.flashcards),
        "quiz_count": len(analysis.quiz),
    })

    return note_path
