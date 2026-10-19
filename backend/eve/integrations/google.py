"""Google Classroom (read-only) and dedicated E.V.E. Google Calendar integration.

OAuth tokens are saved directly to Windows Credential Manager via keyring, never to disk.
Academic integrity constraint: Classroom access is strictly read-only, zero auto-submission.
Calendar constraint: Writes strictly to a dedicated 'E.V.E.' secondary calendar.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession
from sqlmodel import select

from eve.config import Settings
from eve.models import Course, Task

log = logging.getLogger(__name__)

KEYRING_SERVICE = "eve-assistant"
KEYRING_REFRESH_TOKEN_KEY = "google_refresh_token"

CLASSROOM_COURSES_READONLY = "https://www.googleapis.com/auth/classroom.courses.readonly"
CLASSROOM_COURSEWORK_READONLY = "https://www.googleapis.com/auth/classroom.coursework.me.readonly"
# calendar.app.created = create secondary calendars + manage events ONLY on calendars E.V.E. created.
CALENDAR_APP_CREATED = "https://www.googleapis.com/auth/calendar.app.created"
CALENDAR_LIST_READONLY = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
CALENDAR_EVENTS_READONLY = "https://www.googleapis.com/auth/calendar.events.readonly"
GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
DOCS_READONLY = "https://www.googleapis.com/auth/documents.readonly"
DRIVE_METADATA_READONLY = "https://www.googleapis.com/auth/drive.metadata.readonly"
DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
MEET_SPACE_CREATED = "https://www.googleapis.com/auth/meetings.space.created"
IDENTITY_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]

# Each classroom app asks Google only for the permissions it needs (incremental authorization).
APP_SCOPES: dict[str, list[str]] = {
    "classroom": [CLASSROOM_COURSES_READONLY, CLASSROOM_COURSEWORK_READONLY],
    "calendar": [CALENDAR_APP_CREATED, CALENDAR_LIST_READONLY, CALENDAR_EVENTS_READONLY],
    "docs": [DOCS_READONLY, DRIVE_METADATA_READONLY],
    "drive": [DRIVE_READONLY],
    "meet": [MEET_SPACE_CREATED],
    "gmail": [GMAIL_READONLY],
}

SCOPES = [s for scopes in APP_SCOPES.values() for s in scopes]

# Google may return previously-granted scopes alongside new ones (include_granted_scopes).
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

_creds_cache: dict[str, Any] = {"creds": None, "refresh_token": None}


def load_refresh_token() -> str | None:
    """Retrieve OAuth refresh token from Windows Credential Manager."""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_KEY)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed reading token from Windows Credential Manager: %s", exc)
        return None


def save_refresh_token(token: str) -> None:
    """Save OAuth refresh token into Windows Credential Manager."""
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_KEY, token)
        log.info("Google refresh token securely saved to Windows Credential Manager")
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed saving token to Windows Credential Manager: %s", exc)


def clear_refresh_token() -> None:
    """Delete OAuth refresh token from Windows Credential Manager."""
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_KEY)
        log.info("Google refresh token cleared from Windows Credential Manager")
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed deleting token from Windows Credential Manager: %s", exc)


class GoogleAuthManager:
    """Manages Google OAuth2 flow, credential refresh, and Windows Credential Manager storage."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def has_credentials_configured(self) -> bool:
        """Check if OAuth Client ID and Secret (or client_secret.json) are provided."""
        if self.settings.google_client_id and self.settings.google_client_secret:
            return True
        secrets_file = self.settings.google_client_secrets_file or (self.settings.data_dir / "client_secret.json")
        return secrets_file.exists()

    def get_flow(self, redirect_uri: str, scopes: list[str] | None = None, code_verifier: str | None = None) -> Flow:
        """Create OAuth flow from client secret file or config settings.

        ``code_verifier`` must be passed back in on the callback: google-auth-oauthlib
        auto-generates a PKCE verifier when building the login URL, and Google rejects
        the code exchange unless the exact same verifier is presented.
        """
        scopes = scopes or SCOPES
        kwargs: dict[str, Any] = {"scopes": scopes, "redirect_uri": redirect_uri}
        if code_verifier:
            kwargs["code_verifier"] = code_verifier
        secrets_file = self.settings.google_client_secrets_file or (self.settings.data_dir / "client_secret.json")
        if secrets_file.exists():
            return Flow.from_client_secrets_file(str(secrets_file), **kwargs)

        if self.settings.google_client_id and self.settings.google_client_secret:
            client_config = {
                "installed": {
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            return Flow.from_client_config(client_config, **kwargs)

        raise ValueError("Google OAuth credentials not configured. Please supply client_secret.json or client ID/secret.")

    def _client_id_secret(self) -> tuple[str | None, str | None]:
        client_id = self.settings.google_client_id
        client_secret = self.settings.google_client_secret
        secrets_file = self.settings.google_client_secrets_file or (self.settings.data_dir / "client_secret.json")
        if secrets_file.exists() and (not client_id or not client_secret):
            import json

            try:
                data = json.loads(secrets_file.read_text(encoding="utf-8"))
                info = data.get("installed") or data.get("web") or {}
                client_id = client_id or info.get("client_id")
                client_secret = client_secret or info.get("client_secret")
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed parsing client secrets file: %s", exc)
        return client_id, client_secret

    def get_credentials(self) -> Credentials | None:
        """Get valid Credentials using the stored refresh token in Windows Credential Manager."""
        refresh_token = load_refresh_token()
        if not refresh_token:
            _creds_cache.update(creds=None, refresh_token=None)
            return None

        cached = _creds_cache.get("creds")
        if cached is not None and _creds_cache.get("refresh_token") == refresh_token and cached.valid:
            return cached

        client_id, client_secret = self._client_id_secret()
        if not client_id or not client_secret:
            return None

        # No explicit scopes: the refresh returns whatever the user actually granted.
        # Requesting scopes the user never approved would make Google reject the refresh.
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )

        try:
            creds.refresh(Request())
            _creds_cache.update(creds=creds, refresh_token=refresh_token)
            return creds
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed refreshing Google OAuth token: %s", exc)
            return None

    def granted_info(self, creds: Credentials) -> dict[str, Any]:
        """Ask Google which scopes this token really holds (and the account email)."""
        import requests

        try:
            resp = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": creds.token},
                timeout=5,
            )
            if resp.status_code != 200:
                return {"scopes": [], "email": None}
            data = resp.json()
            return {"scopes": data.get("scope", "").split(), "email": data.get("email")}
        except Exception as exc:  # noqa: BLE001
            log.warning("Google tokeninfo lookup failed: %s", exc)
            return {"scopes": [], "email": None}

    def revoke(self) -> None:
        """Revoke the grant at Google (not just locally) and clear the stored token."""
        import requests

        token = load_refresh_token()
        if token:
            try:
                requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=5)
            except Exception as exc:  # noqa: BLE001
                log.warning("Google token revocation request failed: %s", exc)
        clear_refresh_token()
        _creds_cache.update(creds=None, refresh_token=None)


class GoogleIntegrationService:
    """Syncs Google Classroom coursework into Tasks and pushes tasks to dedicated 'E.V.E.' Calendar."""

    def __init__(self, engine: Engine, settings: Settings, auth_manager: GoogleAuthManager) -> None:
        self.engine = engine
        self.settings = settings
        self.auth = auth_manager

    # ---------------------------------------------------------------- Classroom Sync
    def sync_classroom(self, creds: Credentials | None = None) -> dict[str, Any]:
        """Ingest active coursework from Google Classroom into the Tasks table."""
        creds = creds or self.auth.get_credentials()
        if not creds:
            return {"status": "error", "message": "Google account not authenticated."}

        try:
            classroom = build("classroom", "v1", credentials=creds, cache_discovery=False)
            courses_resp = classroom.courses().list(studentId="me", courseStates=["ACTIVE"]).execute()
            courses = courses_resp.get("courses", [])

            scanned = 0
            new_tasks = 0
            updated_tasks = 0

            with DBSession(self.engine) as db:
                for c in courses:
                    cid = c.get("id")
                    cname = c.get("name") or "Course"
                    scanned += 1

                    # Ensure local Course record exists
                    existing_course = db.exec(select(Course).where(Course.name == cname)).first()
                    if not existing_course:
                        existing_course = Course(name=cname)
                        db.add(existing_course)
                        db.commit()
                        db.refresh(existing_course)

                    coursework_resp = classroom.courses().courseWork().list(
                        courseId=cid,
                        courseWorkStates=["PUBLISHED"],
                    ).execute()
                    items = coursework_resp.get("courseWork", [])

                    for cw in items:
                        cw_id = cw.get("id")
                        title = cw.get("title") or "Assignment"

                        # Parse Classroom due date
                        due: datetime | None = None
                        dd = cw.get("dueDate")
                        dt = cw.get("dueTime")
                        if dd and "year" in dd and "month" in dd and "day" in dd:
                            h = dt.get("hours", 23) if dt else 23
                            m = dt.get("minutes", 59) if dt else 59
                            due = datetime(dd["year"], dd["month"], dd["day"], h, m, 0, tzinfo=UTC)

                        # Check for existing task by external_id
                        existing_task = db.exec(
                            select(Task).where(Task.external_id == cw_id)
                        ).first()

                        if not existing_task:
                            # Create new task in 'todo' status
                            task = Task(
                                title=title,
                                due_date=due,
                                status="todo",
                                priority="medium",
                                course_name=cname,
                                evidence=f"Google Classroom: {cname} (ID: {cw_id})",
                                external_id=cw_id,
                                confidence=1.0,
                            )
                            db.add(task)
                            new_tasks += 1
                        else:
                            if due and existing_task.due_date != due:
                                existing_task.due_date = due
                                db.add(existing_task)
                                updated_tasks += 1

                db.commit()

            return {
                "status": "ok",
                "courses_scanned": scanned,
                "new_tasks": new_tasks,
                "updated_tasks": updated_tasks,
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("Google Classroom sync failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    # ---------------------------------------------------------------- Calendar Sync
    def get_or_create_eve_calendar(self, calendar_service: Any) -> str:
        """Locate or safely create the dedicated 'E.V.E.' secondary calendar."""
        cal_list = calendar_service.calendarList().list().execute()
        target_name = self.settings.google_calendar_name or "E.V.E."

        for entry in cal_list.get("items", []):
            if entry.get("summary") == target_name:
                return entry["id"]

        # Create new secondary calendar
        new_cal = calendar_service.calendars().insert(
            body={
                "summary": target_name,
                "description": "Coursework deadlines and academic schedule tracked by E.V.E. AI Assistant.",
                "timeZone": "Asia/Manila",
            }
        ).execute()
        log.info("Created dedicated Google Calendar '%s' with ID %s", target_name, new_cal["id"])
        return new_cal["id"]

    def sync_calendar(self, creds: Credentials | None = None) -> dict[str, Any]:
        """Push confirmed tasks with due dates to the dedicated 'E.V.E.' Google Calendar."""
        creds = creds or self.auth.get_credentials()
        if not creds:
            return {"status": "error", "message": "Google account not authenticated."}

        try:
            cal_service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            cal_id = self.get_or_create_eve_calendar(cal_service)

            events_created = 0

            with DBSession(self.engine) as db:
                # Find tasks due in future that do not have a calendar_event_id yet
                tasks = db.exec(
                    select(Task)
                    .where(Task.due_date != None)  # noqa: E711
                    .where(Task.status.in_(["todo", "doing"]))
                    .where(Task.calendar_event_id == None)  # noqa: E711
                ).all()

                for t in tasks:
                    if not t.due_date:
                        continue
                    start_dt = t.due_date
                    end_dt = t.due_date + timedelta(minutes=30)

                    event_body = {
                        "summary": f"[{t.course_name or 'Coursework'}] {t.title}",
                        "description": (
                            f"Task: {t.title}\n"
                            f"Course: {t.course_name or 'General'}\n"
                            f"Status: {t.status}\n\n"
                            f"Tracked by E.V.E. Personal AI Assistant"
                        ),
                        "start": {
                            "dateTime": start_dt.isoformat(),
                        },
                        "end": {
                            "dateTime": end_dt.isoformat(),
                        },
                    }

                    created_event = cal_service.events().insert(
                        calendarId=cal_id,
                        body=event_body,
                    ).execute()

                    t.calendar_event_id = created_event.get("id")
                    db.add(t)
                    events_created += 1

                db.commit()

            return {
                "status": "ok",
                "calendar_id": cal_id,
                "events_created": events_created,
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("Google Calendar sync failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    # ---------------------------------------------------------------- Docs / Drive / Meet
    def list_recent_docs(self, creds: Credentials, limit: int = 10) -> dict[str, Any]:
        """List the student's most recently modified Google Docs (metadata only)."""
        try:
            drive = build("drive", "v3", credentials=creds, cache_discovery=False)
            resp = drive.files().list(
                q="mimeType='application/vnd.google-apps.document' and trashed=false",
                orderBy="modifiedTime desc",
                pageSize=limit,
                fields="files(id,name,modifiedTime,webViewLink)",
            ).execute()
            return {"status": "ok", "files": resp.get("files", [])}
        except Exception as exc:  # noqa: BLE001
            log.exception("Google Docs listing failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    def list_recent_drive_files(self, creds: Credentials, limit: int = 10) -> dict[str, Any]:
        """List the student's most recently modified Drive files (read-only)."""
        try:
            drive = build("drive", "v3", credentials=creds, cache_discovery=False)
            resp = drive.files().list(
                q="trashed=false",
                orderBy="modifiedTime desc",
                pageSize=limit,
                fields="files(id,name,mimeType,modifiedTime,webViewLink)",
            ).execute()
            return {"status": "ok", "files": resp.get("files", [])}
        except Exception as exc:  # noqa: BLE001
            log.exception("Google Drive listing failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    def create_meet_space(self, creds: Credentials) -> dict[str, Any]:
        """Create a new Google Meet meeting space via the Meet REST API v2."""
        from google.auth.transport.requests import AuthorizedSession

        try:
            session = AuthorizedSession(creds)
            resp = session.post("https://meet.googleapis.com/v2/spaces", json={}, timeout=10)
            if resp.status_code >= 400:
                return {"status": "error", "message": f"Google Meet API error {resp.status_code}: {resp.text[:300]}"}
            data = resp.json()
            return {
                "status": "ok",
                "meeting_uri": data.get("meetingUri"),
                "meeting_code": data.get("meetingCode"),
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("Google Meet space creation failed: %s", exc)
            return {"status": "error", "message": str(exc)}
