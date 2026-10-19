"""Tests for Phase 2: LLM router, Obsidian publishing, relative date parsing, and tasks."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession
from sqlmodel import select

from conftest import EnergyVAD, FakeSTT
from eve.config import Settings
from eve.events import EventBus
from eve.integrations.obsidian import ObsidianPublisher
from eve.llm.prompts import (
    FlashcardItem,
    GlossaryEntry,
    LectureAnalysis,
    QuizQuestion,
    RawExtractedTask,
    TaskExtractionResult,
)
from eve.main import Components, create_app
from eve.models import Course, Flashcard, Note, QuizItem, Segment, Session, Task
from eve.pipelines.lecture import process_session_pipeline
from eve.pipelines.tasks import parse_relative_deadline
from eve.scheduler import ReminderScheduler


class FakeLLMRouter:
    """Mock LLM Router returning realistic structured lecture analysis and extracted tasks."""

    has_cloud = False

    def generate_structured(self, prompt: str, *, system_prompt: str, schema: type[Any]) -> tuple[Any, str]:
        if schema == LectureAnalysis:
            res = LectureAnalysis(
                title="Introduction to Subnetting and IP Addressing",
                summary="Today's lecture introduced IPv4 addressing and the fundamentals of subnetting. The instructor explained the difference between network and host portions of an address.",
                key_takeaways=[
                    "IPv4 addresses are 32-bit values divided into 4 octets.",
                    "Subnet masks distinguish the network bits from host bits.",
                    "Slash notation (CIDR) represents the number of contiguous network mask bits.",
                ],
                glossary=[
                    GlossaryEntry(term="CIDR", definition="Classless Inter-Domain Routing notation (e.g. /24)."),
                    GlossaryEntry(term="Subnet Mask", definition="Bitmask that separates network and host IDs."),
                ],
                flashcards=[
                    FlashcardItem(front="What is a /24 subnet mask in dotted decimal?", back="255.255.255.0", topic="Subnetting"),
                ],
                quiz=[
                    QuizQuestion(
                        question="How many usable host IP addresses are in a /28 subnet?",
                        options=["14", "16", "30", "32"],
                        correct_index=0,
                        explanation="A /28 has 4 host bits (2^4 = 16), minus 2 for network and broadcast = 14 usable hosts.",
                    )
                ],
            )
            return (res, "fake-router")

        if schema == TaskExtractionResult:
            res = TaskExtractionResult(
                tasks=[
                    RawExtractedTask(
                        title="Submit Subnetting Lab 1",
                        due_phrase="this Friday 11:59 PM",
                        priority="high",
                        evidence="Ang deadline ani kay sa Friday ha, before 11:59 PM sa classroom.",
                        confidence=0.95,
                    ),
                    RawExtractedTask(
                        title="Read Chapter 4 OSI Model",
                        due_phrase=None,
                        priority="low",
                        evidence="Basaha ninyo ang chapter 4 later.",
                        confidence=0.60,
                    ),
                ]
            )
            return (res, "fake-router")

        raise ValueError(f"Unexpected schema: {schema}")


def test_relative_deadline_parser():
    # Fixed base date: Monday, October 19, 2026 at 10:00 AM
    base = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

    # 1. "this Friday 11:59 PM" -> Friday, October 23, 2026 23:59
    due_fri = parse_relative_deadline("this Friday 11:59 PM", base)
    assert due_fri is not None
    assert due_fri.year == 2026 and due_fri.month == 10 and due_fri.day == 23
    assert due_fri.hour == 23 and due_fri.minute == 59

    # 2. "tomorrow 5pm" -> Tuesday, October 20, 2026 17:00
    due_tom = parse_relative_deadline("tomorrow 5pm", base)
    assert due_tom is not None
    assert due_tom.day == 20 and due_tom.hour == 17 and due_tom.minute == 0

    # 3. "in 3 days" -> Thursday, October 22, 2026 23:59
    due_in_3 = parse_relative_deadline("in 3 days", base)
    assert due_in_3 is not None
    assert due_in_3.day == 22 and due_in_3.hour == 23

    # 4. None / empty
    assert parse_relative_deadline(None, base) is None
    assert parse_relative_deadline("", base) is None


def test_obsidian_publisher_atomic_and_path_containment(tmp_path):
    vault = tmp_path / "Obsidian Vault"
    vault.mkdir()
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models",
                 vault_path=vault, lecture_folder="13 - Lectures", _env_file=None)

    publisher = ObsidianPublisher(s)

    session = Session(
        id=1,
        title="Intro to Computer Networks",
        consent_confirmed=True,
        started_at=datetime(2026, 10, 19, 9, 30, 0, tzinfo=UTC),
    )
    analysis = LectureAnalysis(
        title="Intro to Computer Networks",
        summary="A comprehensive overview of computer network topologies and architectures.",
        key_takeaways=["Star topology is standard in LANs."],
        glossary=[GlossaryEntry(term="LAN", definition="Local Area Network.")],
        flashcards=[FlashcardItem(front="What is a LAN?", back="Local Area Network", topic="Networking")],
        quiz=[QuizQuestion(question="What is a LAN?", options=["Local", "Wide", "Metropolitan", "Global"],
                           correct_index=0, explanation="Local Area Network")],
    )
    segments = [
        Segment(session_id=1, source="them", t0=0.0, t1=12.5, text="Maayong buntag, today we start networking."),
        Segment(session_id=1, source="me", t0=13.0, t1=15.0, text="Good morning sir."),
    ]
    tasks = [
        RawExtractedTask(title="Assignment 1", due_phrase="next Friday", priority="medium",
                         evidence="Submit next Friday", confidence=0.9),
    ]

    note_path = publisher.publish_lecture_note(session, "IT 222", analysis, tasks, segments)
    assert note_path.exists()
    assert note_path.name == "2026-10-19 - Intro to Computer Networks.md"

    # Verify Markdown content
    content = note_path.read_text(encoding="utf-8")
    assert "tags:" in content
    assert "course/it-222" in content
    assert "## 1. Executive Summary" in content
    assert "A comprehensive overview" in content
    assert "## 3. Technical Glossary" in content
    assert "| **LAN** |" in content
    assert "## 4. Coursework Deadlines" in content
    assert "Assignment 1" in content
    assert "## 5. Study Flashcards" in content
    assert "## 6. Comprehension Practice Quiz" in content
    # Verify path containment guard raises ValueError if target escapes vault
    publisher.lectures_dir = tmp_path.parent
    with pytest.raises(ValueError, match="resolves outside of Obsidian vault"):
        publisher.publish_lecture_note(session, "OutsideVault", analysis, tasks, segments)


def test_session_processing_pipeline_end_to_end(tmp_path):
    vault = tmp_path / "Obsidian Vault"
    vault.mkdir()
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models",
                 vault_path=vault, lecture_folder="13 - Lectures", _env_file=None)
    s.ensure_dirs()

    from eve.db import make_engine
    engine = make_engine(s.db_path)
    import asyncio
    loop = asyncio.new_event_loop()
    bus = EventBus(loop)
    router = FakeLLMRouter()

    # Create test session and segments in database
    with DBSession(engine) as db:
        course = Course(name="IT 222 Networking")
        db.add(course)
        db.commit()
        db.refresh(course)

        session = Session(title="Subnetting Lecture", course_id=course.id, consent_confirmed=True)
        db.add(session)
        db.commit()
        db.refresh(session)
        sid = session.id

        seg1 = Segment(session_id=sid, source="them", t0=0.0, t1=10.0, text="Karon atong i-discuss ang subnetting.")
        seg2 = Segment(session_id=sid, source="them", t0=10.5, t1=20.0, text="Ang deadline sa assignment kay sa Friday ha.")
        db.add(seg1)
        db.add(seg2)
        db.commit()

    note_path = process_session_pipeline(sid, engine, s, router, bus)
    assert note_path.exists()

    # Verify database persistence
    with DBSession(engine) as db:
        session_row = db.get(Session, sid)
        assert session_row.status == "processed"

        note_row = db.exec(select(Note).where(Note.session_id == sid)).first()
        assert note_row is not None
        assert "IPv4" in note_row.summary

        task_rows = db.exec(select(Task).where(Task.session_id == sid)).all()
        assert len(task_rows) == 2
        high_conf = next(t for t in task_rows if t.title == "Submit Subnetting Lab 1")
        assert high_conf.status == "todo"
        assert high_conf.due_date is not None
        low_conf = next(t for t in task_rows if t.title == "Read Chapter 4 OSI Model")
        assert low_conf.status == "inbox"  # routed to inbox due to confidence < 0.7

        cards = db.exec(select(Flashcard).where(Flashcard.session_id == sid)).all()
        assert len(cards) >= 1

        quizzes = db.exec(select(QuizItem).where(QuizItem.session_id == sid)).all()
        assert len(quizzes) >= 1
        assert quizzes[0].correct_index == 0


def test_phase2_api_endpoints(tmp_path):
    vault = tmp_path / "Obsidian Vault"
    vault.mkdir()
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models",
                 vault_path=vault, lecture_folder="13 - Lectures", _env_file=None)

    from conftest import FakeCapture

    comps = Components(
        load_stt=lambda _s: FakeSTT(),
        capture_factory=lambda _s: lambda _clock: FakeCapture([]),
        vad_factory=EnergyVAD,
        list_devices=lambda: [],
        router_factory=lambda _s: FakeLLMRouter(),
    )

    with TestClient(create_app(s, comps)) as client:
        token = client.app.state.api_token
        auth = {"Authorization": f"Bearer {token}"}

        # 1. Start and stop a session
        r = client.post("/api/sessions/start", json={"title": "Web Dev", "course": "IT 311", "consent_confirmed": True}, headers=auth)
        assert r.status_code == 200
        sid = r.json()["id"]

        # Insert a transcript segment directly
        with DBSession(client.app.state.engine) as db:
            db.add(Segment(session_id=sid, source="them", t0=0.0, t1=5.0, text="Laravel routes and controllers."))
            db.commit()

        client.post("/api/sessions/stop", headers=auth)

        # 2. Process session
        r_proc = client.post(f"/api/sessions/{sid}/process", headers=auth)
        assert r_proc.status_code == 200
        proc_data = r_proc.json()
        assert proc_data["tasks_count"] == 2
        assert proc_data["flashcards_count"] >= 1
        assert proc_data["quiz_count"] >= 1

        # 3. Retrieve note
        r_note = client.get(f"/api/sessions/{sid}/note", headers=auth)
        assert r_note.status_code == 200
        assert len(r_note.json()["key_takeaways"]) >= 1

        # 4. Retrieve flashcards & quiz
        r_cards = client.get(f"/api/sessions/{sid}/flashcards", headers=auth)
        assert r_cards.status_code == 200 and len(r_cards.json()) >= 1

        r_quiz = client.get(f"/api/sessions/{sid}/quiz", headers=auth)
        assert r_quiz.status_code == 200 and len(r_quiz.json()) >= 1

        # 5. List and update tasks
        r_tasks = client.get("/api/tasks", headers=auth)
        assert r_tasks.status_code == 200
        tasks = r_tasks.json()
        assert len(tasks) == 2

        task_id = tasks[0]["id"]
        r_up = client.post(f"/api/tasks/{task_id}/status", json={"status": "done"}, headers=auth)
        assert r_up.status_code == 200
        assert r_up.json()["status"] == "done"


def test_reminder_scheduler(tmp_path):
    from eve.db import make_engine
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    s.ensure_dirs()
    engine = make_engine(s.db_path)

    import asyncio
    loop = asyncio.new_event_loop()
    bus = EventBus(loop)
    scheduler = ReminderScheduler(engine, bus, interval_minutes=60)

    # Insert task due in 2 hours
    with DBSession(engine) as db:
        now = datetime.now(UTC)
        task = Task(title="Urgent Quiz", due_date=now + timedelta(hours=2), status="todo", course_name="IT 222")
        db.add(task)
        db.commit()
        db.refresh(task)
        tid = task.id

    notified = scheduler.check_deadlines()
    assert tid in notified

    # Second check within 12 hours skips duplicate alert
    notified_again = scheduler.check_deadlines()
    assert tid not in notified_again
