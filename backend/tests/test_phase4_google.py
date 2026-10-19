"""Tests for Phase 4: Google Classroom read-only sync and dedicated E.V.E. Calendar integration."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession
from sqlmodel import select

from conftest import EnergyVAD, FakeSTT
from eve.config import Settings
from eve.db import make_engine
from eve.integrations.google import (
    GoogleAuthManager,
    GoogleIntegrationService,
    clear_refresh_token,
    load_refresh_token,
    save_refresh_token,
)
from eve.main import Components, create_app
from eve.models import Course, Task


def test_keyring_token_storage():
    with patch("eve.integrations.google.keyring") as mock_keyring:
        store = {}
        mock_keyring.set_password.side_effect = lambda s, u, p: store.update({(s, u): p})
        mock_keyring.get_password.side_effect = lambda s, u: store.get((s, u))
        mock_keyring.delete_password.side_effect = lambda s, u: store.pop((s, u), None)

        test_token = "test_refresh_token_abc_123"
        save_refresh_token(test_token)
        assert load_refresh_token() == test_token

        clear_refresh_token()
        assert load_refresh_token() is None


def test_google_auth_manager_unconfigured(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    mgr = GoogleAuthManager(s)
    assert mgr.has_credentials_configured() is False
    assert mgr.get_credentials() is None


def test_classroom_sync_deduplication(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    s.ensure_dirs()
    engine = make_engine(s.db_path)
    mgr = GoogleAuthManager(s)

    service = GoogleIntegrationService(engine, s, mgr)

    # Mock Classroom API responses
    mock_creds = MagicMock()
    mock_classroom = MagicMock()
    mock_courses = MagicMock()
    mock_coursework = MagicMock()

    mock_classroom.courses.return_value = mock_courses
    mock_courses.list.return_value.execute.return_value = {
        "courses": [{"id": "c101", "name": "IT 222 Computer Networking"}]
    }
    mock_courses.courseWork.return_value = mock_coursework
    mock_coursework.list.return_value.execute.return_value = {
        "courseWork": [
            {
                "id": "cw_sub_01",
                "title": "Subnetting Configuration Assignment",
                "dueDate": {"year": 2026, "month": 10, "day": 25},
                "dueTime": {"hours": 23, "minutes": 59},
            }
        ]
    }

    with patch("eve.integrations.google.build", return_value=mock_classroom):
        # 1. Initial sync creates the task
        res1 = service.sync_classroom(mock_creds)
        assert res1["status"] == "ok"
        assert res1["new_tasks"] == 1

        with DBSession(engine) as db:
            tasks = db.exec(select(Task).where(Task.external_id == "cw_sub_01")).all()
            assert len(tasks) == 1
            t = tasks[0]
            assert t.title == "Subnetting Configuration Assignment"
            assert t.course_name == "IT 222 Computer Networking"
            assert t.status == "todo"
            assert t.due_date is not None
            assert t.due_date.year == 2026

        # 2. Second sync does not duplicate the task (idempotency)
        res2 = service.sync_classroom(mock_creds)
        assert res2["status"] == "ok"
        assert res2["new_tasks"] == 0
        assert res2["updated_tasks"] == 0

        with DBSession(engine) as db:
            tasks = db.exec(select(Task).where(Task.external_id == "cw_sub_01")).all()
            assert len(tasks) == 1


def test_calendar_sync_dedicated_calendar(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    s.ensure_dirs()
    engine = make_engine(s.db_path)
    mgr = GoogleAuthManager(s)

    service = GoogleIntegrationService(engine, s, mgr)

    # Insert task with due date needing calendar sync
    with DBSession(engine) as db:
        task = Task(
            title="OSI Layer Quiz 2",
            due_date=datetime(2026, 10, 26, 14, 0, 0, tzinfo=UTC),
            status="todo",
            course_name="IT 222",
            calendar_event_id=None,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        tid = task.id

    # Mock Calendar API
    mock_creds = MagicMock()
    mock_cal_api = MagicMock()
    mock_cal_list = MagicMock()
    mock_calendars = MagicMock()
    mock_events = MagicMock()

    mock_cal_api.calendarList.return_value = mock_cal_list
    # Simulate secondary calendar 'E.V.E.' already existing
    mock_cal_list.list.return_value.execute.return_value = {
        "items": [{"id": "eve_cal_sec_id_999", "summary": "E.V.E."}]
    }
    mock_cal_api.events.return_value = mock_events
    mock_events.insert.return_value.execute.return_value = {"id": "gcal_event_555"}

    with patch("eve.integrations.google.build", return_value=mock_cal_api):
        res = service.sync_calendar(mock_creds)
        assert res["status"] == "ok"
        assert res["events_created"] == 1
        assert res["calendar_id"] == "eve_cal_sec_id_999"

        # Verify task was updated with calendar_event_id
        with DBSession(engine) as db:
            updated_task = db.get(Task, tid)
            assert updated_task is not None
            assert updated_task.calendar_event_id == "gcal_event_555"

        # Second sync does not re-create event
        res2 = service.sync_calendar(mock_creds)
        assert res2["status"] == "ok"
        assert res2["events_created"] == 0


def test_phase4_api_endpoints(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    s.ensure_dirs()
    from conftest import FakeCapture

    comps = Components(
        load_stt=lambda _s: FakeSTT(),
        capture_factory=lambda _s: lambda _clock: FakeCapture([]),
        vad_factory=EnergyVAD,
        list_devices=lambda: [],
    )

    with TestClient(create_app(s, comps)) as client:
        token = client.app.state.api_token
        auth = {"Authorization": f"Bearer {token}"}

        # 1. Status endpoint
        r_status = client.get("/api/integrations/google/status", headers=auth)
        assert r_status.status_code == 200
        data = r_status.json()
        assert data["calendar_name"] == "E.V.E."
        assert data["authenticated"] is False

        # 2. Sync without auth fails gracefully with 401
        r_sync = client.post("/api/integrations/google/sync", headers=auth)
        assert r_sync.status_code == 401

        # 3. Disconnect endpoint
        r_disc = client.post("/api/integrations/google/disconnect", headers=auth)
        assert r_disc.status_code == 200
