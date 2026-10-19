"""Structured schemas and prompt templates for lecture analysis and task extraction."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- Schemas
class FlashcardItem(BaseModel):
    front: str = Field(description="Clear, specific question or concept prompt on the card front")
    back: str = Field(description="Comprehensive explanation or answer on back")
    topic: str | None = Field(default=None, description="Topic tag (e.g. Subnetting, OSI Model, Database)")


class QuizQuestion(BaseModel):
    question: str = Field(description="Multiple-choice question")
    options: list[str] = Field(min_length=4, max_length=4, description="Exactly 4 distinct options (A, B, C, D)")
    correct_index: int = Field(ge=0, le=3, description="0-based index of the correct option")
    explanation: str = Field(description="Why this option is correct and others are incorrect")


class GlossaryEntry(BaseModel):
    term: str = Field(description="Technical or academic term")
    definition: str = Field(description="Clear explanation as used in the lecture")


class LectureAnalysis(BaseModel):
    title: str = Field(description="Specific descriptive title for this lecture session")
    summary: str = Field(description="Comprehensive lecture summary (3-6 detailed paragraphs in English)")
    key_takeaways: list[str] = Field(description="6-10 bullet points covering core concepts taught")
    glossary: list[GlossaryEntry] = Field(description="Key technical terminology defined in class")
    flashcards: list[FlashcardItem] = Field(description="6-12 flashcard Q&As for active recall study")
    quiz: list[QuizQuestion] = Field(description="5-10 multiple choice practice questions")


class RawExtractedTask(BaseModel):
    title: str = Field(description="Actionable task title (e.g. 'Submit Lab 3 Subnetting Worksheet')")
    due_phrase: str | None = Field(default=None, description="Spoken deadline phrase as heard (e.g. 'this Friday 11:59 PM', 'next Tuesday')")
    priority: str = Field(default="medium", description="Priority level: 'high' (exam/major project), 'medium' (assignment/lab), 'low' (reading)")
    evidence: str = Field(description="Exact transcript quote where the professor announced this")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score that this is an actionable assignment deadline (0.0 to 1.0)")


class TaskExtractionResult(BaseModel):
    tasks: list[RawExtractedTask] = Field(description="All extracted coursework tasks or assignments announced in the lecture")


# ---------------------------------------------------------------- Prompts
LECTURE_SYSTEM_PROMPT = """You are E.V.E., an expert academic personal assistant for a BS Information Technology student (Software Development & Networking) at USTP.
The lecture transcript provided may contain a natural mix of Bisaya (Cebuano), Tagalog/Taglish, and English spoken by the instructor and students.

Guidelines:
1. Accurately understand the instructor's Bisaya, Tagalog, and English instructions and lessons.
2. Synthesize the final summary, key takeaways, glossary, flashcards, and quiz in clear, high-craft, professional English.
3. In the summary, explain both conceptual foundations and practical implementation details mentioned in class.
4. Avoid AI slop: do not output vague filler sentences. Focus on actual technical topics, equations, code, diagrams, network concepts, or algorithms taught in class.
5. Create flashcards and quiz questions that test deep comprehension (understanding 'why' and 'how'), not trivial word recall.
"""

LECTURE_USER_PROMPT = """Course: {course}
Session Title: {title}
Session Date: {date}

Transcript:
\"\"\"
{transcript}
\"\"\"

Please analyze the lecture and produce the structured output according to the schema.
"""

TASK_SYSTEM_PROMPT = """You are E.V.E.'s automated academic deadline and coursework task extractor.
Inspect the following lecture transcript carefully for any announcements made by the professor or teacher regarding:
- Homework assignments, worksheets, labs, or exercises
- Project submissions, milestones, or proposals
- Upcoming quizzes, midterms, finals, or defense dates
- Reading assignments or required preparation for the next meeting

Rules:
1. Pay close attention to mixed Bisaya/Tagalog/English announcement patterns, for example:
   - "Ang deadline ani kay sa Friday ha..." (The deadline for this is on Friday...)
   - "I-submit ninyo sa classroom before 11:59 PM..." (Submit in classroom before 11:59 PM...)
   - "Next week Tuesday naa tay short quiz..." (Next week Tuesday we have a short quiz...)
2. Extract the exact evidence quote from the transcript.
3. Estimate confidence from 0.0 to 1.0 (assign < 0.7 if the deadline is ambiguous or uncertain).
4. If no assignments or deadlines were mentioned, return an empty tasks list.
"""

TASK_USER_PROMPT = """Course: {course}
Lecture Date: {date}

Transcript:
\"\"\"
{transcript}
\"\"\"

Extract all announced coursework tasks and deadlines.
"""
