"""Voice Assistant tool-calling brain.

Translates spoken or text requests into structured tool executions over an allowlisted,
safety-bounded registry (no arbitrary code execution or shell commands).
Synthesizes spoken replies with Kokoro-ONNX TTS.
"""

from __future__ import annotations

import base64
import datetime
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession, col, desc, select

from eve.config import Settings, get_settings
from eve.llm.router import LLMRouter
from eve.models import Note, QuizItem, Session, Task
from eve.voice.tts import TTSEngine

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM_PROMPT = """You are E.V.E. (Extensible Virtual Entity), a personal local-first AI assistant for Joe, a BSIT student at USTP.
You have access to a safe set of tools to control study workflows, track coursework, search past lectures, and quiz the student.

Available tools:
1. start_session: Begins recording a lecture or study call. Arguments: title (string), course (string or null).
2. stop_session: Stops the active recording session and begins transcription/note processing. Arguments: none.
3. add_task: Adds a new coursework task or assignment deadline. Arguments: title (string), due_date (ISO string or null), course (string or null).
4. list_deadlines: Lists pending deadlines and coursework. Arguments: limit (integer, default 5).
5. ask_lectures: Performs hybrid RAG search across past lectures to answer study questions. Arguments: question (string).
6. summarize_last_session: Retrieves the key points and summary from the most recent lecture. Arguments: none.
7. quiz_me: Retrieves a practice quiz question from past lectures. Arguments: course (string or null).
8. general_answer: Used for general conversation, explanations, greetings, or questions not requiring a system tool. Arguments: none.

Guidelines:
- Keep your `spoken_response` brief, natural, conversational, and direct (1-3 sentences) suitable for audio playback.
- If the user asks about lecture material, use `ask_lectures`.
- If the user asks "what's due" or "what are my deadlines", use `list_deadlines`.
- If the user says "start recording lecture for Web Development", use `start_session`.
- If the user says "stop recording", use `stop_session`.
"""


class AssistantAction(BaseModel):
    tool: Literal[
        "start_session",
        "stop_session",
        "add_task",
        "list_deadlines",
        "ask_lectures",
        "summarize_last_session",
        "quiz_me",
        "general_answer",
    ] = Field(description="The tool to execute.")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value arguments for the chosen tool.",
    )
    spoken_response: str = Field(
        description="Concise, friendly natural language response to be spoken aloud.",
    )


class AssistantResponse(BaseModel):
    tool: str
    arguments: dict[str, Any]
    response_text: str
    tool_output: dict[str, Any] = Field(default_factory=dict)
    audio_base64: str | None = None


class VoiceAssistant:
    """Voice Assistant coordinator with allowlisted tool execution and TTS synthesis."""

    def __init__(
        self,
        engine: Any,
        router: LLMRouter,
        settings: Settings | None = None,
        tts: TTSEngine | None = None,
        session_manager: Any | None = None,
    ) -> None:
        self.engine = engine
        self.router = router
        self.settings = settings or get_settings()
        self.tts = tts or TTSEngine(self.settings)
        self.session_manager = session_manager

    def process_command(
        self,
        user_input: str,
        *,
        synthesize_audio: bool = True,
    ) -> AssistantResponse:
        """Processes a voice or text command from the user."""
        logger.info("Processing voice assistant command: '%s'", user_input)

        # 1. Ask LLM to pick tool & draft spoken reply
        action, provider = self.router.generate_structured(
            prompt=f"User command: {user_input}",
            system_prompt=ASSISTANT_SYSTEM_PROMPT,
            schema=AssistantAction,
        )

        tool_output: dict[str, Any] = {}
        final_spoken_text = action.spoken_response

        # 2. Execute selected tool safely
        try:
            if action.tool == "start_session":
                tool_output = self._tool_start_session(action.arguments)
            elif action.tool == "stop_session":
                tool_output = self._tool_stop_session()
            elif action.tool == "add_task":
                tool_output = self._tool_add_task(action.arguments)
            elif action.tool == "list_deadlines":
                tool_output = self._tool_list_deadlines(action.arguments)
                if tool_output.get("tasks"):
                    titles = [f"{t['title']} due {t['due_date'] or 'soon'}" for t in tool_output["tasks"][:3]]
                    final_spoken_text = f"You have {len(tool_output['tasks'])} pending items: {'; '.join(titles)}."
                else:
                    final_spoken_text = "You currently have no pending deadlines. All caught up!"
            elif action.tool == "ask_lectures":
                tool_output = self._tool_ask_lectures(action.arguments.get("question", user_input))
                if tool_output.get("answer"):
                    final_spoken_text = tool_output["answer"]
            elif action.tool == "summarize_last_session":
                tool_output = self._tool_summarize_last_session()
                if tool_output.get("summary"):
                    final_spoken_text = f"Summary for {tool_output['title']}: {tool_output['summary']}"
            elif action.tool == "quiz_me":
                tool_output = self._tool_quiz_me(action.arguments.get("course"))
                if tool_output.get("question"):
                    final_spoken_text = f"Here is a question on {tool_output.get('course', 'your coursework')}: {tool_output['question']}"
            elif action.tool == "general_answer":
                tool_output = {"status": "ok"}
        except Exception as exc:
            logger.error("Error executing tool %s: %s", action.tool, exc)
            tool_output = {"error": str(exc)}
            final_spoken_text = f"I encountered an issue executing that command: {exc}"

        # 3. Optional TTS Audio Synthesis
        audio_b64: str | None = None
        if synthesize_audio and self.tts:
            try:
                wav_bytes = self.tts.synthesize_wav_bytes(final_spoken_text)
                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
            except Exception as exc:
                logger.debug("Failed to synthesize TTS audio: %s", exc)

        return AssistantResponse(
            tool=action.tool,
            arguments=action.arguments,
            response_text=final_spoken_text,
            tool_output=tool_output,
            audio_base64=audio_b64,
        )

    # ---------------------------------------------------------------- Tool Implementations
    def _tool_start_session(self, args: dict[str, Any]) -> dict[str, Any]:
        title = args.get("title") or "Voice Started Lecture"
        course = args.get("course")
        if self.session_manager:
            session = self.session_manager.start(title=title, course=course)
            return {"status": "started", "session_id": session.id, "title": session.title}
        return {"status": "simulated_started", "title": title, "course": course}

    def _tool_stop_session(self) -> dict[str, Any]:
        if self.session_manager:
            session_id = self.session_manager.stop()
            return {"status": "stopped", "session_id": session_id}
        return {"status": "simulated_stopped"}

    def _tool_add_task(self, args: dict[str, Any]) -> dict[str, Any]:
        title = args.get("title", "Untitled Task")
        due_str = args.get("due_date")
        course = args.get("course")

        due_dt = None
        if due_str:
            try:
                due_dt = datetime.datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                pass

        with DBSession(self.engine) as db:
            task = Task(
                title=title,
                course_name=course,
                due_date=due_dt,
                status="todo",
                priority="medium",
                confidence=1.0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return {"status": "created", "task_id": task.id, "title": task.title}

    def _tool_list_deadlines(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = int(args.get("limit", 5))
        with DBSession(self.engine) as db:
            tasks = db.exec(
                select(Task)
                .where(Task.status.in_(["inbox", "todo", "doing"]))
                .order_by(col(Task.due_date).asc().nulls_last())
                .limit(limit)
            ).all()
            return {
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "course": t.course_name,
                        "due_date": t.due_date.isoformat() if t.due_date else None,
                        "status": t.status,
                    }
                    for t in tasks
                ]
            }

    def _tool_ask_lectures(self, question: str) -> dict[str, Any]:
        from eve.rag.chat import HybridRAGSearcher
        from eve.rag.embeddings import EmbeddingEngine

        emb_engine = EmbeddingEngine(self.settings)
        searcher = HybridRAGSearcher(self.engine, emb_engine)
        ans = searcher.answer_question(question, router=self.router, top_k=3)
        return {
            "answer": ans.answer,
            "citations": [c.model_dump() for c in ans.citations],
        }

    def _tool_summarize_last_session(self) -> dict[str, Any]:
        with DBSession(self.engine) as db:
            note = db.exec(
                select(Note).order_by(col(Note.created_at).desc()).limit(1)
            ).first()
            if not note:
                return {"summary": "No recorded sessions found in the archive yet."}
            return {
                "session_id": note.session_id,
                "title": note.title,
                "summary": note.summary,
            }

    def _tool_quiz_me(self, course: str | None = None) -> dict[str, Any]:
        with DBSession(self.engine) as db:
            query = select(QuizItem)
            items = db.exec(query.limit(20)).all()
            if not items:
                return {"question": "No quiz items generated yet. Record a lecture first to generate practice quizzes!"}
            import random
            selected = random.choice(items)
            return {
                "id": selected.id,
                "question": selected.question,
                "options": selected.options_json,
                "explanation": selected.explanation,
            }
