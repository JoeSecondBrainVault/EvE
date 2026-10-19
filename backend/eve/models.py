"""Persistent data models (Courses, Sessions, Transcript Segments, Notes, Tasks, Flashcards, Quizzes)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Course(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=120)
    created_at: datetime = Field(default_factory=utcnow)


class Session(SQLModel, table=True):
    """One recorded call or lecture."""

    id: int | None = Field(default=None, primary_key=True)
    course_id: int | None = Field(default=None, foreign_key="course.id", index=True)
    title: str = Field(max_length=200)
    status: str = Field(default="recording", max_length=20)  # recording | stopped | failed | processed
    consent_confirmed: bool = False
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    recording_dir: str | None = None


class Segment(SQLModel, table=True):
    """One transcribed utterance. ``t0``/``t1`` are seconds from session start."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    source: str = Field(max_length=10)  # "them" (system audio) | "me" (microphone)
    t0: float
    t1: float
    text: str
    language: str | None = Field(default=None, max_length=8)
    avg_logprob: float | None = None


class Note(SQLModel, table=True):
    """Generated Obsidian lecture note metadata and content."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True, unique=True)
    vault_path: str = Field(max_length=500)
    title: str = Field(max_length=200)
    summary: str
    key_points_json: str = Field(default="[]")   # JSON array of bullet points
    glossary_json: str = Field(default="{}")     # JSON dict of term -> definition
    created_at: datetime = Field(default_factory=utcnow)


class Task(SQLModel, table=True):
    """Extracted coursework task, assignment, quiz, or project deadline."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int | None = Field(default=None, foreign_key="session.id", index=True)
    title: str = Field(max_length=300)
    due_date: datetime | None = None
    status: str = Field(default="inbox", max_length=20)  # inbox | todo | doing | done
    priority: str = Field(default="medium", max_length=10)  # low | medium | high
    course_name: str | None = Field(default=None, max_length=120)
    evidence: str | None = None  # Exact transcript quote supporting this task
    confidence: float = 1.0     # Detection confidence (0.0 to 1.0)
    external_id: str | None = Field(default=None, index=True)  # Google Classroom courseWork.id
    calendar_event_id: str | None = Field(default=None)        # Google Calendar event ID
    created_at: datetime = Field(default_factory=utcnow)
    reminded_at: datetime | None = None


class Flashcard(SQLModel, table=True):
    """Study flashcard generated from lecture key concepts."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    front: str
    back: str
    topic: str | None = Field(default=None, max_length=100)


class QuizItem(SQLModel, table=True):
    """Self-test quiz question with multiple-choice answers."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    question: str
    options_json: str     # JSON array of strings
    correct_index: int   # 0-based index of correct option
    explanation: str


class Chunk(SQLModel, table=True):
    """Text chunk representing ~60s of lecture speech for hybrid RAG search."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    course_name: str | None = Field(default=None, index=True)
    session_title: str | None = Field(default=None)
    t0: float
    t1: float
    text: str
    embedding_json: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)

