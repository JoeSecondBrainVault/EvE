"""Background task reminder scheduler using APScheduler and Windows winotify toasts."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession
from sqlmodel import select

from eve.events import EventBus
from eve.models import Task

log = logging.getLogger(__name__)


def show_toast(title: str, msg: str) -> None:
    """Send native Windows notification toast if on Windows platform."""
    if sys.platform != "win32":
        return
    try:
        from winotify import Notification

        toast = Notification(
            app_id="E.V.E. Assistant",
            title=title[:60],
            msg=msg[:150],
        )
        toast.show()
    except Exception as exc:  # noqa: BLE001
        log.debug("Toast notification skipped: %s", exc)


class ReminderScheduler:
    """Checks for approaching coursework deadlines and issues toast alerts."""

    def __init__(self, engine: Engine, bus: EventBus, interval_minutes: int = 15) -> None:
        self.engine = engine
        self.bus = bus
        self.interval_minutes = interval_minutes
        self._scheduler = BackgroundScheduler(daemon=True)

    def start(self) -> None:
        self._scheduler.add_job(
            self.check_deadlines,
            "interval",
            minutes=self.interval_minutes,
            id="eve_task_reminders",
            replace_existing=True,
        )
        self._scheduler.start()
        log.info("Reminder scheduler started (polling every %d mins)", self.interval_minutes)

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def add_periodic_job(self, job_fn: Any, job_id: str, minutes: int = 30) -> None:
        self._scheduler.add_job(
            job_fn,
            "interval",
            minutes=minutes,
            id=job_id,
            replace_existing=True,
        )

    def check_deadlines(self) -> list[int]:
        """Scan active tasks and send alerts for deadlines approaching within 72 hours."""
        now = datetime.now(UTC)
        threshold = now + timedelta(days=3)
        notified_ids: list[int] = []

        with DBSession(self.engine) as db:
            tasks = db.exec(
                select(Task)
                .where(Task.status.in_(["inbox", "todo", "doing"]))
                .where(Task.due_date != None)  # noqa: E711
                .where(Task.due_date <= threshold)
                .where(Task.due_date >= now - timedelta(hours=2))
            ).all()

            for task in tasks:
                # If reminded recently (within 12 hours), skip
                if task.reminded_at and (now - task.reminded_at.replace(tzinfo=UTC)) < timedelta(hours=12):
                    continue

                diff = (task.due_date.replace(tzinfo=UTC) - now).total_seconds()
                hours_left = max(0.0, diff / 3600.0)

                course_tag = f"[{task.course_name}] " if task.course_name else ""
                if hours_left < 2:
                    time_desc = "due in less than 2 hours!"
                elif hours_left < 24:
                    time_desc = f"due in {int(hours_left)} hours"
                else:
                    time_desc = f"due in {int(hours_left // 24)} days"

                toast_title = f"⚠️ Coursework Reminder: {task.title}"
                toast_msg = f"{course_tag}{time_desc}. Click to open Obsidian note or dashboard."

                show_toast(toast_title, toast_msg)

                self.bus.publish({
                    "type": "task_reminder",
                    "task_id": task.id,
                    "title": task.title,
                    "course": task.course_name,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "hours_left": round(hours_left, 1),
                })

                task.reminded_at = now
                db.add(task)
                notified_ids.append(task.id)

            if notified_ids:
                db.commit()

        return notified_ids
