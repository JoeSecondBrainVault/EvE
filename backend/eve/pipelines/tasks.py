"""Coursework and deadline extraction pipeline with relative-date resolution."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, time, timedelta

from eve.llm.prompts import (
    TASK_SYSTEM_PROMPT,
    TASK_USER_PROMPT,
    RawExtractedTask,
    TaskExtractionResult,
)
from eve.llm.router import LLMRouter

log = logging.getLogger(__name__)

_DAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def parse_relative_deadline(phrase: str | None, base_date: datetime) -> datetime | None:
    """Parse relative academic deadline phrases ('next Friday', 'this coming Friday 11:59 PM').

    Calculated relative to base_date (session started_at timestamp).
    """
    if not phrase:
        return None

    text = phrase.lower().strip()

    # Default deadline time: end of day 23:59:00
    target_time = time(23, 59, 0)
    time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = time_match.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        target_time = time(min(23, hour), min(59, minute), 0)

    # Ensure base_date is timezone-aware
    if base_date.tzinfo is None:
        base_date = base_date.replace(tzinfo=UTC)

    # 1. "today" / "tonight"
    if "today" in text or "tonight" in text:
        return datetime.combine(base_date.date(), target_time, tzinfo=UTC)

    # 2. "tomorrow"
    if "tomorrow" in text:
        target_date = base_date.date() + timedelta(days=1)
        return datetime.combine(target_date, target_time, tzinfo=UTC)

    # 3. "in N days"
    in_days_match = re.search(r"in\s+(\d+)\s+days?", text)
    if in_days_match:
        target_date = base_date.date() + timedelta(days=int(in_days_match.group(1)))
        return datetime.combine(target_date, target_time, tzinfo=UTC)

    # 4. "in N weeks"
    in_weeks_match = re.search(r"in\s+(\d+)\s+weeks?", text)
    if in_weeks_match:
        target_date = base_date.date() + timedelta(weeks=int(in_weeks_match.group(1)))
        return datetime.combine(target_date, target_time, tzinfo=UTC)

    # 5. Day of week matching ("Friday", "this Friday", "next Tuesday")
    for day_name, day_idx in _DAYS.items():
        pattern = rf"\b(?:this\s+|next\s+|coming\s+)?{day_name}\b"
        if re.search(pattern, text):
            current_day = base_date.weekday()
            days_ahead = (day_idx - current_day) % 7
            is_next = "next" in text

            if days_ahead == 0 and not is_next:
                # "this Friday" said on Friday -> today
                days_ahead = 0
            elif days_ahead == 0 and is_next:
                days_ahead = 7
            elif is_next and days_ahead < 7:
                days_ahead += 7
            elif days_ahead <= 0:
                days_ahead += 7

            target_date = base_date.date() + timedelta(days=days_ahead)
            return datetime.combine(target_date, target_time, tzinfo=UTC)

    return None


def extract_tasks_from_transcript(
    router: LLMRouter,
    transcript: str,
    course_name: str | None,
    session_date: datetime,
) -> list[RawExtractedTask]:
    """Analyze lecture transcript with LLMRouter to extract coursework tasks."""
    if not transcript.strip():
        return []

    date_str = session_date.strftime("%Y-%m-%d %A")
    user_prompt = TASK_USER_PROMPT.format(
        course=course_name or "General Coursework",
        date=date_str,
        transcript=transcript,
    )

    try:
        result, provider = router.generate_structured(
            user_prompt,
            system_prompt=TASK_SYSTEM_PROMPT,
            schema=TaskExtractionResult,
        )
        log.info("Extracted %d tasks using %s", len(result.tasks), provider)
        return result.tasks
    except Exception as exc:  # noqa: BLE001
        log.warning("Task extraction failed (%s); returning empty tasks", exc)
        return []
