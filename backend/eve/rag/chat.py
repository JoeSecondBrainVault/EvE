"""Hybrid RAG search (BM25 + vector) and grounded question answering with timestamp citations."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import numpy as np
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession, select

from eve.llm.router import LLMRouter
from eve.models import Chunk
from eve.rag.embeddings import EmbeddingEngine

log = logging.getLogger(__name__)


def format_seconds(seconds: float) -> str:
    """Format float seconds as MM:SS (or HH:MM:SS if >= 1 hour)."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class Citation(BaseModel):
    chunk_id: int
    session_id: int
    course_name: str | None
    session_title: str | None
    t0: float
    t1: float
    timestamp_label: str
    snippet: str


class ScoredChunk(BaseModel):
    chunk_id: int
    session_id: int
    course_name: str | None
    session_title: str | None
    t0: float
    t1: float
    text: str
    score: float


class RAGAnswer(BaseModel):
    answer: str
    citations: list[Citation]


RAG_SYSTEM_PROMPT = """You are E.V.E., an intelligent personal study assistant.
Answer the student's question accurately and concisely using ONLY the provided lecture excerpts.
Guidelines:
1. Base your answer strictly on the facts in the excerpts. Do not hallucinate or make assumptions.
2. Cite your sources inline using the source number or course timestamp, e.g. [Source 1] or [Networking, 04:15].
3. If the provided excerpts do not contain enough information to answer, state clearly: "This topic was not discussed in the recorded lectures."
4. If the lecture was in mixed Bisaya/Tagalog/English, explain the concepts clearly in English while acknowledging original terms when helpful.
"""


class HybridRAGSearcher:
    """Combines SQLite FTS5 (BM25) and sqlite-vec (or cosine fallback) via Reciprocal Rank Fusion."""

    def __init__(self, engine: Engine, embedding_engine: EmbeddingEngine) -> None:
        self.engine = engine
        self.embedding_engine = embedding_engine

    def search(
        self,
        query: str,
        course_filter: str | None = None,
        top_k: int = 5,
    ) -> list[ScoredChunk]:
        """Perform hybrid search returning the top-K highest-ranked chunks."""
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        # 1. BM25 Search via chunks_fts
        bm25_ranks: dict[int, int] = {}
        tokens = re.findall(r"\w+", cleaned_query)
        if tokens:
            fts_query = " OR ".join(f'"{t}"' for t in tokens)
            try:
                with self.engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            """
                            SELECT chunk_id, rank
                            FROM chunks_fts
                            WHERE chunks_fts MATCH :query
                            ORDER BY rank
                            LIMIT 30
                            """
                        ),
                        {"query": fts_query},
                    ).fetchall()
                    for rank_idx, r in enumerate(rows):
                        try:
                            cid = int(r[0])
                            bm25_ranks[cid] = rank_idx + 1
                        except (ValueError, TypeError):
                            continue
            except Exception as exc:  # noqa: BLE001
                log.debug("BM25 query failed (%s); continuing with vector search", exc)

        # 2. Vector Search via chunks_vec or cosine fallback
        vec_ranks: dict[int, int] = {}
        query_vec = self.embedding_engine.embed_query(cleaned_query)
        vec_str = json.dumps(query_vec)

        used_sqlite_vec = False
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT chunk_id, distance
                        FROM chunks_vec
                        WHERE embedding MATCH :vec_str AND k = 30
                        ORDER BY distance ASC
                        """
                    ),
                    {"vec_str": vec_str},
                ).fetchall()
                if rows:
                    used_sqlite_vec = True
                    for rank_idx, r in enumerate(rows):
                        try:
                            cid = int(r[0])
                            vec_ranks[cid] = rank_idx + 1
                        except (ValueError, TypeError):
                            continue
        except Exception as exc:  # noqa: BLE001
            log.debug("sqlite-vec search failed (%s); using cosine fallback", exc)

        # Cosine fallback if sqlite-vec was not available or empty
        if not used_sqlite_vec:
            try:
                with DBSession(self.engine) as db:
                    chunks = db.exec(select(Chunk)).all()
                    if chunks:
                        q_arr = np.array(query_vec, dtype=np.float32)
                        scored_list: list[tuple[int, float]] = []
                        for c in chunks:
                            if c.id is None or not c.embedding_json:
                                continue
                            try:
                                emb = np.array(json.loads(c.embedding_json), dtype=np.float32)
                                sim = float(np.dot(q_arr, emb))
                                scored_list.append((c.id, sim))
                            except Exception:
                                continue
                        scored_list.sort(key=lambda x: x[1], reverse=True)
                        for rank_idx, (cid, _) in enumerate(scored_list[:30]):
                            vec_ranks[cid] = rank_idx + 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Cosine fallback failed: %s", exc)

        # 3. Reciprocal Rank Fusion (RRF)
        # score = 1 / (60 + rank_bm25) + 1 / (60 + rank_vec)
        all_cids = set(bm25_ranks.keys()) | set(vec_ranks.keys())
        rrf_scores: dict[int, float] = {}
        for cid in all_cids:
            score = 0.0
            if cid in bm25_ranks:
                score += 1.0 / (60.0 + bm25_ranks[cid])
            if cid in vec_ranks:
                score += 1.0 / (60.0 + vec_ranks[cid])
            rrf_scores[cid] = score

        if not rrf_scores:
            return []

        sorted_cids = sorted(rrf_scores.keys(), key=lambda c: rrf_scores[c], reverse=True)

        # Fetch Chunk objects from DB
        results: list[ScoredChunk] = []
        with DBSession(self.engine) as db:
            for cid in sorted_cids:
                chunk = db.get(Chunk, cid)
                if not chunk:
                    continue
                if course_filter and chunk.course_name:
                    if course_filter.lower() not in chunk.course_name.lower():
                        continue

                results.append(
                    ScoredChunk(
                        chunk_id=chunk.id or cid,
                        session_id=chunk.session_id,
                        course_name=chunk.course_name,
                        session_title=chunk.session_title,
                        t0=chunk.t0,
                        t1=chunk.t1,
                        text=chunk.text,
                        score=round(rrf_scores[cid], 5),
                    )
                )
                if len(results) >= top_k:
                    break

        return results

    def answer_question(
        self,
        query: str,
        course_filter: str | None = None,
        router: LLMRouter | None = None,
        top_k: int = 4,
    ) -> RAGAnswer:
        """Find relevant lecture chunks and synthesize a cited answer."""
        chunks = self.search(query, course_filter=course_filter, top_k=top_k)

        if not chunks:
            return RAGAnswer(
                answer="No relevant lecture excerpts were found in your recorded coursework.",
                citations=[],
            )

        citations: list[Citation] = []
        context_blocks: list[str] = []

        for idx, c in enumerate(chunks, 1):
            ts_label = format_seconds(c.t0)
            citations.append(
                Citation(
                    chunk_id=c.chunk_id,
                    session_id=c.session_id,
                    course_name=c.course_name,
                    session_title=c.session_title,
                    t0=c.t0,
                    t1=c.t1,
                    timestamp_label=ts_label,
                    snippet=c.text[:140] + "..." if len(c.text) > 140 else c.text,
                )
            )
            context_blocks.append(
                f"[Source {idx}]: Course: {c.course_name or 'General'} | "
                f"Session: {c.session_title or 'Untitled'} | "
                f"Timestamp: {ts_label}\n"
                f"Transcript Excerpt: {c.text}"
            )

        context_str = "\n\n".join(context_blocks)
        user_prompt = f"""Student Question: {query}

Lecture Excerpts:
{context_str}

Please answer the question based on the lecture excerpts above, citing sources with [Source N]."""

        if router is not None:
            try:
                answer_text, _ = router.generate(user_prompt, system_prompt=RAG_SYSTEM_PROMPT)
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM generation failed in RAG chat (%s); returning excerpts summary", exc)
                answer_text = (
                    f"Found {len(chunks)} relevant excerpt(s) in your lectures:\n\n"
                    + "\n\n".join(f"- **{c.course_name or 'Lecture'} ({format_seconds(c.t0)})**: {c.text}" for c in chunks)
                )
        else:
            answer_text = (
                f"Relevant lecture excerpt ({chunks[0].course_name or 'Lecture'} at {format_seconds(chunks[0].t0)}):\n\n"
                f'"{chunks[0].text}"'
            )

        return RAGAnswer(answer=answer_text, citations=citations)
