"""Automated tests for Phase 6: Assignment Helper, System Tray, Retention, and Rate Limiting."""

from __future__ import annotations

import io
import time
from pathlib import Path
from unittest.mock import MagicMock

import docx
import pypdf
import pytest
from fastapi.testclient import TestClient

from eve.config import Settings
from eve.db import make_engine
from eve.events import EventBus
from eve.main import Components, create_app
from eve.pipelines.assignments import (
    ACADEMIC_INTEGRITY_NOTICE,
    AssignmentAnalysis,
    AssignmentHelper,
    OutlineSection,
    RubricItem,
    extract_text_from_file_bytes,
)
from eve.retention import SlidingWindowRateLimiter, purge_expired_recordings
from eve.tray import create_tray_icon_image


# --- 1. Document Text Extraction Tests ---
def test_extract_text_plain_text():
    text_content = b"Assignment 1: Database Normalization\nDesign 3NF tables."
    extracted = extract_text_from_file_bytes("prompt.txt", text_content)
    assert "Assignment 1" in extracted
    assert "3NF tables" in extracted

    md_content = b"# Lab 2\nImplement Dijkstra's Algorithm."
    extracted_md = extract_text_from_file_bytes("rubric.md", md_content)
    assert "Dijkstra" in extracted_md


def test_extract_text_docx():
    doc = docx.Document()
    doc.add_heading("Coursework Rubric", level=1)
    doc.add_paragraph("Criteria: Clean Architecture, Unit Tests >= 80%.")
    buf = io.BytesIO()
    doc.save(buf)
    content = buf.getvalue()

    extracted = extract_text_from_file_bytes("guidelines.docx", content)
    assert "Coursework Rubric" in extracted
    assert "Unit Tests >= 80%" in extracted


def test_extract_text_pdf():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    content = buf.getvalue()

    # Empty/blank page returns empty or string without crash
    extracted = extract_text_from_file_bytes("spec.pdf", content)
    assert isinstance(extracted, str)


def test_extract_text_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported file format"):
        extract_text_from_file_bytes("malicious.exe", b"binary content")


# --- 2. Rate Limiting Tests ---
def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=1.0)
    client = "127.0.0.1"

    assert limiter.is_allowed(client) is True
    assert limiter.is_allowed(client) is True
    assert limiter.is_allowed(client) is True
    # 4th request in same window must be blocked
    assert limiter.is_allowed(client) is False

    # Different client is not blocked
    assert limiter.is_allowed("192.168.1.1") is True

    # Reset allows again
    limiter.reset()
    assert limiter.is_allowed(client) is True


# --- 3. Audio Retention Cleaner Tests ---
def test_purge_expired_recordings(tmp_path: Path):
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir(parents=True)

    # 1. Old session folder (40 days old)
    old_folder = rec_dir / "20260801-100000-1-old_lecture"
    old_folder.mkdir()
    old_wav = old_folder / "them.wav"
    old_wav.write_bytes(b"\x00" * 1024)  # 1 KB
    old_note = old_folder / "notes.txt"
    old_note.write_text("Preserved notes")

    # Set mtime to 40 days ago
    past_time = time.time() - (40 * 86400)
    import os
    os.utime(old_folder, (past_time, past_time))

    # 2. Recent session folder (2 days old)
    recent_folder = rec_dir / "20261017-100000-2-recent_lecture"
    recent_folder.mkdir()
    recent_wav = recent_folder / "them.wav"
    recent_wav.write_bytes(b"\x00" * 2048)  # 2 KB

    purged_count, freed_bytes = purge_expired_recordings(rec_dir, retention_days=30)

    assert purged_count == 1
    assert freed_bytes == 1024
    assert not old_wav.exists()
    assert old_note.exists()  # Non-wav files are preserved
    assert recent_wav.exists()  # Recent audio is preserved


# --- 4. System Tray Icon Generation Tests ---
def test_tray_icon_generation():
    img_idle = create_tray_icon_image("idle")
    assert img_idle.size == (64, 64)
    assert img_idle.mode == "RGBA"

    img_rec = create_tray_icon_image("recording")
    assert img_rec.size == (64, 64)

    img_proc = create_tray_icon_image("processing")
    assert img_proc.size == (64, 64)


# --- 5. Assignment Helper Pipeline & API Endpoints ---
def test_assignment_helper_structured_generation(tmp_path: Path):
    mock_router = MagicMock()
    mock_analysis = AssignmentAnalysis(
        title="Database Systems Normalization Lab",
        course_name="IT 312",
        summary="Normalize unnormalized tables to 3NF.",
        deliverables=["ERD diagram (PDF)", "SQL Schema file"],
        rubric_criteria=[
            RubricItem(criterion="3NF Conformance", expectation="Zero transitive dependencies")
        ],
        outline_sections=[
            OutlineSection(
                section_title="Step 1: 1NF Atomic Attributes",
                recommended_content=["Eliminate repeating groups", "Identify primary key"],
                lecture_connection="Lecture 4: Relational Algebra",
            )
        ],
        suggested_citations=[],
        draft_overview="Start by inspecting the unnormalized spreadsheet...",
        academic_integrity_notice=ACADEMIC_INTEGRITY_NOTICE,
    )
    mock_router.generate_structured.return_value = (mock_analysis, "gemini")

    engine = make_engine(tmp_path / "test.db")
    helper = AssignmentHelper(engine, mock_router, Settings(data_dir=tmp_path))

    res = helper.analyze_assignment("Please normalize these student records", course_filter="IT 312")
    assert res.title == "Database Systems Normalization Lab"
    assert len(res.deliverables) == 2
    assert "ACADEMIC_INTEGRITY_NOTICE" in res.academic_integrity_notice or "Do not submit directly" in res.academic_integrity_notice


def test_api_assignment_endpoints(tmp_path: Path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        vault_path=tmp_path / "vault",
        retention_days=30,
        rate_limit_chat_rpm=5,
    )
    settings.ensure_dirs()

    comps = Components(
        load_stt=lambda s: MagicMock(device="cpu"),
        capture_factory=lambda s: lambda clock: MagicMock(sources=["them", "me"]),
        vad_factory=lambda: MagicMock(return_value=0.0),
        list_devices=lambda: [],
        router_factory=lambda s: MagicMock(),
    )

    app = create_app(settings, comps)

    # Mock the assignment helper
    mock_analysis = AssignmentAnalysis(
        title="Web Systems Project",
        course_name="IT 222",
        summary="Create REST API with FastAPI and Next.js.",
        deliverables=["GitHub Repo link", "Architecture Diagram"],
        rubric_criteria=[],
        outline_sections=[
            OutlineSection(
                section_title="Backend Scaffold",
                recommended_content=["Define Pydantic models", "Setup CORS"],
            )
        ],
        suggested_citations=[],
        draft_overview="Draft outline for student revision.",
        academic_integrity_notice=ACADEMIC_INTEGRITY_NOTICE,
    )

    with TestClient(app) as client:
        app.state.assignment_helper.analyze_assignment = MagicMock(return_value=mock_analysis)
        token = app.state.api_token
        # 1. Analyze prompt endpoint
        resp = client.post(
            "/api/assignments/analyze",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "Build a REST API in Python", "course": "IT 222"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Web Systems Project"
        assert len(data["deliverables"]) == 2

        # 2. Upload file endpoint
        file_bytes = b"Build a REST API in Python with endpoints for tasks."
        resp_upload = client.post(
            "/api/assignments/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("project_spec.txt", file_bytes, "text/plain")},
            data={"course": "IT 222"},
        )
        assert resp_upload.status_code == 200
        assert resp_upload.json()["title"] == "Web Systems Project"

        # 3. Retention manual purge endpoint
        resp_purge = client.post(
            "/api/retention/purge",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_purge.status_code == 200
        assert resp_purge.json()["status"] == "ok"
        assert "purged_count" in resp_purge.json()


def test_api_rate_limiting_enforcement(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        vault_path=tmp_path / "vault",
        rate_limit_chat_rpm=2,  # Limit to 2 requests per minute
    )
    settings.ensure_dirs()

    comps = Components(
        load_stt=lambda s: MagicMock(device="cpu"),
        capture_factory=lambda s: lambda clock: MagicMock(sources=["them", "me"]),
        vad_factory=lambda: MagicMock(return_value=0.0),
        list_devices=lambda: [],
        router_factory=lambda s: MagicMock(),
    )

    app = create_app(settings, comps)

    # Mock the assignment helper
    mock_analysis = AssignmentAnalysis(
        title="Test",
        summary="Test",
        deliverables=[],
        rubric_criteria=[],
        outline_sections=[],
        draft_overview="Test",
        academic_integrity_notice=ACADEMIC_INTEGRITY_NOTICE,
    )

    with TestClient(app) as client:
        app.state.assignment_helper.analyze_assignment = MagicMock(return_value=mock_analysis)
        token = app.state.api_token
        # Request 1: OK
        r1 = client.post(
            "/api/assignments/analyze",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "req 1"},
        )
        assert r1.status_code == 200

        # Request 2: OK
        r2 = client.post(
            "/api/assignments/analyze",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "req 2"},
        )
        assert r2.status_code == 200

        # Request 3: 429 Too Many Requests
        r3 = client.post(
            "/api/assignments/analyze",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "req 3"},
        )
        assert r3.status_code == 429
        assert "Rate limit exceeded" in r3.json()["detail"]
