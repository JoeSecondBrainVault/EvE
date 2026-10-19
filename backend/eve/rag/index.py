"""Lecture chunking, FTS5 full-text indexing, and sqlite-vec vector indexing."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession
from sqlmodel import select

from eve.models import Chunk, Course, Segment, Session
from eve.rag.embeddings import EmbeddingEngine

log = logging.getLogger(__name__)


def init_rag_tables(engine: Engine) -> None:
    """Create FTS5 full-text and sqlite-vec vector virtual tables if they do not exist."""
    with engine.begin() as conn:
        # FTS5 for BM25 keyword search
        try:
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        text,
                        course_name,
                        session_title,
                        tokenize = 'unicode61'
                    );
                    """
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not initialize chunks_fts virtual table: %s", exc)

        # sqlite-vec for KNN vector similarity
        try:
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                        chunk_id INTEGER PRIMARY KEY,
                        embedding float[768]
                    );
                    """
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not initialize chunks_vec virtual table: %s", exc)


def chunk_session_segments(
    segments: list[Segment],
    window_s: float = 60.0,
    overlap_s: float = 10.0,
) -> list[dict[str, Any]]:
    """Group chronological lecture segments into ~60-second overlapping windows."""
    if not segments:
        return []

    sorted_segs = sorted(segments, key=lambda s: s.t0)
    chunks: list[dict[str, Any]] = []
    n = len(sorted_segs)
    i = 0

    while i < n:
        w_start = sorted_segs[i].t0
        w_end_target = w_start + window_s
        texts: list[str] = []
        last_t1 = sorted_segs[i].t1

        j = i
        while j < n and sorted_segs[j].t0 < w_end_target:
            seg_text = sorted_segs[j].text.strip()
            if seg_text:
                texts.append(seg_text)
            last_t1 = max(last_t1, sorted_segs[j].t1)
            j += 1

        combined_text = " ".join(texts).strip()
        if combined_text:
            chunks.append({
                "t0": round(w_start, 2),
                "t1": round(last_t1, 2),
                "text": combined_text,
            })

        # Advance window by (window_s - overlap_s)
        advance_target = w_start + max(5.0, window_s - overlap_s)
        next_i = i + 1
        while next_i < n and sorted_segs[next_i].t0 < advance_target:
            next_i += 1
        i = next_i if next_i > i else i + 1

    return chunks


def index_session_chunks(
    session_id: int,
    engine: Engine,
    embedding_engine: EmbeddingEngine,
    window_s: float = 60.0,
    overlap_s: float = 10.0,
) -> int:
    """Extract, embed, and index chunks for a completed lecture session."""
    with DBSession(engine) as db:
        session = db.get(Session, session_id)
        if not session:
            log.warning("Cannot index session %d: not found", session_id)
            return 0

        session_title = session.title
        course_name: str | None = None
        if session.course_id:
            course = db.get(Course, session.course_id)
            if course:
                course_name = course.name

        segments = db.exec(
            select(Segment)
            .where(Segment.session_id == session_id)
            .order_by(Segment.t0)
        ).all()

        if not segments:
            log.info("Session %d has no segments to index", session_id)
            return 0

        raw_chunks = chunk_session_segments(segments, window_s=window_s, overlap_s=overlap_s)
        if not raw_chunks:
            return 0

        # Compute embeddings for all chunks in batch
        texts = [c["text"] for c in raw_chunks]
        embeddings = embedding_engine.embed_texts(texts)

        # Delete old chunks for this session
        existing_chunks = db.exec(
            select(Chunk).where(Chunk.session_id == session_id)
        ).all()
        old_ids = [c.id for c in existing_chunks if c.id is not None]

        for c in existing_chunks:
            db.delete(c)
        db.commit()

    # Remove from virtual tables
    with engine.begin() as conn:
        for old_id in old_ids:
            try:
                conn.execute(text("DELETE FROM chunks_fts WHERE chunk_id = :id"), {"id": str(old_id)})
            except Exception:
                pass
            try:
                conn.execute(text("DELETE FROM chunks_vec WHERE chunk_id = :id"), {"id": old_id})
            except Exception:
                pass

        # Insert new chunks
        with DBSession(engine) as db:
            new_chunk_objs: list[Chunk] = []
            for item, emb in zip(raw_chunks, embeddings, strict=False):
                obj = Chunk(
                    session_id=session_id,
                    course_name=course_name,
                    session_title=session_title,
                    t0=item["t0"],
                    t1=item["t1"],
                    text=item["text"],
                    embedding_json=json.dumps(emb),
                )
                db.add(obj)
                new_chunk_objs.append(obj)
            db.commit()
            for obj in new_chunk_objs:
                db.refresh(obj)

    # Insert into virtual tables
    with engine.begin() as conn:
        for obj in new_chunk_objs:
            if obj.id is None:
                continue
            emb_str = obj.embedding_json or "[]"
            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO chunks_fts (chunk_id, text, course_name, session_title)
                        VALUES (:cid, :text, :cname, :stitle)
                        """
                    ),
                    {
                        "cid": str(obj.id),
                        "text": obj.text,
                        "cname": obj.course_name or "",
                        "stitle": obj.session_title or "",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("Failed inserting into chunks_fts: %s", exc)

            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO chunks_vec (chunk_id, embedding)
                        VALUES (:cid, :emb)
                        """
                    ),
                    {"cid": obj.id, "emb": emb_str},
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("Failed inserting into chunks_vec: %s", exc)

    log.info("Indexed %d chunks for session %d into hybrid RAG", len(new_chunk_objs), session_id)
    return len(new_chunk_objs)
