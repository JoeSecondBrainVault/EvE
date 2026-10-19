"""Obsidian Second Brain Integration: publishes rich Markdown notes into 13 - Lectures/."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

from eve.config import Settings
from eve.llm.prompts import LectureAnalysis, RawExtractedTask
from eve.models import Segment, Session

log = logging.getLogger(__name__)

_SAFE_CHAR = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str, fallback: str = "untitled") -> str:
    cleaned = _SAFE_CHAR.sub("", name).strip(" .")
    return cleaned[:100] or fallback


def format_seconds(s: float) -> str:
    m = int(s // 60)
    sec = int(s % 60)
    return f"{m:02d}:{sec:02d}"


class ObsidianPublisher:
    """Safely and atomically writes lecture notes to the Obsidian Second Brain."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.vault_path = settings.vault_path.resolve()
        self.lectures_dir = settings.lectures_dir.resolve()

    def publish_lecture_note(
        self,
        session: Session,
        course_name: str | None,
        analysis: LectureAnalysis,
        tasks: list[RawExtractedTask],
        segments: list[Segment],
    ) -> Path:
        """Render and save an Obsidian Markdown note with YAML frontmatter."""
        course_clean = safe_filename(course_name or "General", fallback="General")
        course_dir = (self.lectures_dir / course_clean).resolve()

        # Enforce path containment within vault (prevent directory traversal)
        if not course_dir.is_relative_to(self.vault_path):
            raise ValueError(f"Target path {course_dir} resolves outside of Obsidian vault {self.vault_path}")

        course_dir.mkdir(parents=True, exist_ok=True)

        session_date = session.started_at.strftime("%Y-%m-%d")
        title_clean = safe_filename(analysis.title or session.title, fallback="Session")
        filename = f"{session_date} - {title_clean}.md"
        target_path = course_dir / filename

        # Double check target path containment
        if not target_path.resolve().is_relative_to(self.vault_path):
            raise ValueError(f"Target file {target_path} escapes Obsidian vault")

        content = self._render_markdown(session, course_name, analysis, tasks, segments)

        # Atomic file write via temporary file
        tmp_path = target_path.with_suffix(".md.tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, target_path)
            log.info("Published Obsidian lecture note: %s", target_path)
            return target_path
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _render_markdown(
        self,
        session: Session,
        course_name: str | None,
        analysis: LectureAnalysis,
        tasks: list[RawExtractedTask],
        segments: list[Segment],
    ) -> str:
        date_str = session.started_at.strftime("%Y-%m-%d")
        time_str = session.started_at.strftime("%H:%M:%S")
        course_tag = re.sub(r"\s+", "-", (course_name or "general").lower())

        # Calculate speaker duration stats
        them_count = sum(1 for s in segments if s.source == "them")
        me_count = sum(1 for s in segments if s.source == "me")
        total_utts = max(1, len(segments))
        them_pct = round((them_count / total_utts) * 100)
        me_pct = 100 - them_pct

        total_duration_m = 0.0
        if segments:
            total_duration_m = round(max(s.t1 for s in segments) / 60.0, 1)

        lines: list[str] = [
            "---",
            "tags:",
            "  - lecture",
            f"  - course/{course_tag}",
            "  - eve-generated",
            f"created: {date_str}",
            f"session_id: {session.id}",
            f"course: \"[[{course_name or 'General'}]]\"",
            f"duration_minutes: {total_duration_m}",
            f"speaker_ratio_them_me: \"{them_pct}% / {me_pct}%\"",
            "---",
            "",
            f"# {analysis.title}",
            "",
            f"> **Course**: [[{course_name or 'General'}]]  ",
            f"> **Date & Time**: {date_str} {time_str} | **Duration**: {total_duration_m} mins  ",
            f"> **Participants**: Instructor / Speaker ({them_pct}%), You ({me_pct}%)",
            "",
            "## 1. Executive Summary",
            analysis.summary,
            "",
            "## 2. Key Takeaways & Core Concepts",
        ]

        for pt in analysis.key_takeaways:
            lines.append(f"- {pt}")
        lines.append("")

        if analysis.glossary:
            lines.extend([
                "## 3. Technical Glossary",
                "| Term | Definition & Classroom Context |",
                "| :--- | :--- |",
            ])
            for item in analysis.glossary:
                clean_term = item.term.replace("|", "/")
                clean_def = item.definition.replace("|", "/")
                lines.append(f"| **{clean_term}** | {clean_def} |")
            lines.append("")

        if tasks:
            lines.extend([
                "## 4. Coursework Deadlines & Action Items",
                "> [!IMPORTANT] Discovered in Lecture Transcript",
                "",
            ])
            for t in tasks:
                due_info = f" (Due: **{t.due_phrase}**)" if t.due_phrase else ""
                lines.append(f"- [ ] **{t.title}**{due_info}  ")
                lines.append(f"  > *Evidence Quote*: \"{t.evidence}\" (Confidence: {int(t.confidence * 100)}%)")
            lines.append("")

        if analysis.flashcards:
            lines.extend([
                "## 5. Study Flashcards (Active Recall)",
            ])
            for i, fc in enumerate(analysis.flashcards, 1):
                topic = f" ({fc.topic})" if fc.topic else ""
                lines.append(f"> [!NOTE] Flashcard {i}{topic}")
                lines.append(f"> **Q**: {fc.front}")
                lines.append("> ")
                lines.append(f"> **A**: {fc.back}")
                lines.append("")

        if analysis.quiz:
            lines.extend([
                "## 6. Comprehension Practice Quiz",
            ])
            for i, q in enumerate(analysis.quiz, 1):
                lines.append(f"### Question {i}")
                lines.append(f"**{q.question}**\n")
                letters = ["A", "B", "C", "D"]
                for j, opt in enumerate(q.options):
                    mark = "*(Correct)*" if j == q.correct_index else ""
                    lines.append(f"- **{letters[j]}**) {opt} {mark}")
                lines.append("")
                lines.append(f"> [!TIP] Explanation")
                lines.append(f"> {q.explanation}")
                lines.append("")

        lines.extend([
            "## 7. Transcript Record",
            "<details><summary>Click to view full chronological transcript</summary>",
            "",
        ])
        for seg in segments:
            who = "**Instructor / Speaker**" if seg.source == "them" else "**You**"
            ts = f"[{format_seconds(seg.t0)} - {format_seconds(seg.t1)}]"
            lines.append(f"- `{ts}` {who}: {seg.text}")

        lines.extend([
            "",
            "</details>",
            "",
        ])

        return "\n".join(lines)
