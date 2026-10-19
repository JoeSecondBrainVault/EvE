"""Assignment Helper: document analysis, lecture RAG grounding, rubric breakdown, and draft outline generator.

Analyzes uploaded PDFs, DOCXs, or prompt text safely through in-memory libraries (pypdf, python-docx),
retrieves relevant lecture notes via Hybrid RAG, and produces structured analysis and outlines.
Enforces strict Academic Integrity boundaries (drafts marked for student revision; zero auto-submission).
"""

from __future__ import annotations

import io
import logging
from typing import Any

from pydantic import BaseModel, Field

from eve.config import Settings, get_settings
from eve.llm.router import LLMRouter

logger = logging.getLogger(__name__)

ACADEMIC_INTEGRITY_NOTICE = (
    "NOTICE: Generated strictly as a personal study and revision reference. "
    "Do not submit directly. Review, edit, and expand into your own original coursework."
)

ASSIGNMENT_SYSTEM_PROMPT = f"""You are the Assignment Helper for Joe, a BSIT student at USTP.
Analyze the provided assignment prompt/rubric alongside relevant lecture excerpts.
Your goal is to organize the assignment, provide clarity, outline the recommended solution, and cite concepts from past lectures.

Guidelines:
- Identify explicit deliverables, constraints, and rubric expectations.
- Link concepts to the provided past lecture excerpts with citations where appropriate.
- Provide a structured, well-organized section-by-section outline.
- If drafting sample text or structure, ensure it is clearly outlined and adheres to academic integrity: {ACADEMIC_INTEGRITY_NOTICE}
"""


class RubricItem(BaseModel):
    criterion: str
    expectation: str


class OutlineSection(BaseModel):
    section_title: str
    recommended_content: list[str]
    lecture_connection: str | None = None


class LectureCitationRef(BaseModel):
    topic: str
    citation_label: str
    relevance: str


class AssignmentAnalysis(BaseModel):
    title: str = Field(description="Assignment or project title.")
    course_name: str | None = Field(default=None, description="Inferred course name.")
    summary: str = Field(description="Executive summary of what the assignment requires.")
    deliverables: list[str] = Field(description="List of required deliverables and file formats.")
    rubric_criteria: list[RubricItem] = Field(
        default_factory=list,
        description="Key evaluation criteria and grading weights.",
    )
    outline_sections: list[OutlineSection] = Field(
        description="Logical section-by-section outline to complete the coursework.",
    )
    suggested_citations: list[LectureCitationRef] = Field(
        default_factory=list,
        description="Relevant topics and timestamps from past lectures.",
    )
    draft_overview: str = Field(
        description="Comprehensive draft outline and walkthrough for student revision.",
    )
    academic_integrity_notice: str = Field(default=ACADEMIC_INTEGRITY_NOTICE)


def extract_text_from_file_bytes(filename: str, content: bytes) -> str:
    """Safely extracts text from PDF, DOCX, or plain text bytes without executing shell commands."""
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content))
            pages_text = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages_text).strip()
        except Exception as exc:
            logger.error("Failed to extract text from PDF %s: %s", filename, exc)
            raise ValueError(f"Could not parse PDF document: {exc}") from exc

    elif lower_name.endswith(".docx"):
        try:
            import docx

            doc = docx.Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            return "\n\n".join(paragraphs).strip()
        except Exception as exc:
            logger.error("Failed to extract text from DOCX %s: %s", filename, exc)
            raise ValueError(f"Could not parse Word document: {exc}") from exc

    elif lower_name.endswith((".txt", ".md")):
        try:
            return content.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            raise ValueError(f"Could not parse text file: {exc}") from exc

    raise ValueError("Unsupported file format. Please upload a .pdf, .docx, .txt, or .md file.")


class AssignmentHelper:
    """Processes coursework materials and produces grounded research and outlines."""

    def __init__(
        self,
        engine: Any,
        router: LLMRouter,
        settings: Settings | None = None,
    ) -> None:
        self.engine = engine
        self.router = router
        self.settings = settings or get_settings()

    def analyze_assignment(
        self,
        prompt_text: str,
        course_filter: str | None = None,
    ) -> AssignmentAnalysis:
        """Analyzes an assignment prompt against historical lecture notes and generates study outlines."""
        if not prompt_text.strip():
            raise ValueError("Assignment text or prompt cannot be empty.")

        # 1. Hybrid RAG retrieval of relevant lecture concepts
        rag_citations: list[dict[str, Any]] = []
        rag_context = ""
        try:
            from eve.rag.chat import HybridRAGSearcher
            from eve.rag.embeddings import EmbeddingEngine

            emb_engine = EmbeddingEngine(self.settings)
            searcher = HybridRAGSearcher(self.engine, emb_engine)
            # Use the first 500 characters of the prompt as query
            search_query = prompt_text[:500]
            chunks = searcher.search(search_query, course_filter=course_filter, top_k=4)
            if chunks:
                rag_context = "\n\nRelevant past lecture excerpts:\n" + "\n".join(
                    f"- [{c.course_name or 'General'} {c.session_title or ''}]: {c.text}" for c in chunks
                )
        except Exception as exc:
            logger.debug("RAG lookup during assignment analysis skipped: %s", exc)

        full_prompt = (
            f"Assignment Prompt & Requirements:\n{prompt_text}\n"
            f"{rag_context}\n\n"
            f"Specified Course: {course_filter or 'Auto-detect from prompt'}"
        )

        analysis, provider = self.router.generate_structured(
            prompt=full_prompt,
            system_prompt=ASSIGNMENT_SYSTEM_PROMPT,
            schema=AssignmentAnalysis,
        )
        return analysis
