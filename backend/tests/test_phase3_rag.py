"""Tests for Phase 3: RAG chunking, hybrid BM25 + vector search, chat answering, and API."""

from __future__ import annotations


import numpy as np
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession

from conftest import EnergyVAD, FakeSTT
from eve.config import Settings
from eve.db import make_engine
from eve.main import Components, create_app
from eve.models import Course, Segment, Session, Task
from eve.rag.chat import HybridRAGSearcher, format_seconds
from eve.rag.embeddings import EmbeddingEngine
from eve.rag.index import chunk_session_segments, index_session_chunks


class FakeRouterForRAG:
    has_cloud = False

    def generate(self, prompt: str, *, system_prompt: str) -> tuple[str, str]:
        return "Subnetting divides an IP network into smaller sub-networks [Source 1].", "mock"


def test_format_seconds():
    assert format_seconds(0.0) == "00:00"
    assert format_seconds(65.0) == "01:05"
    assert format_seconds(3665.0) == "01:01:05"


def test_chunk_session_segments():
    segs = [
        Segment(session_id=1, source="them", t0=0.0, t1=25.0, text="Introduction to IPv4 addresses and octets."),
        Segment(session_id=1, source="them", t0=30.0, t1=55.0, text="A subnet mask defines network and host bits."),
        Segment(session_id=1, source="them", t0=65.0, t1=85.0, text="Slash 24 means 24 network bits and 8 host bits."),
    ]
    chunks = chunk_session_segments(segs, window_s=60.0, overlap_s=10.0)
    assert len(chunks) >= 1
    first = chunks[0]
    assert first["t0"] == 0.0
    assert "IPv4" in first["text"]
    assert "subnet mask" in first["text"]


def test_embedding_engine(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    engine = EmbeddingEngine(s)
    embs = engine.embed_texts(["hello world", "computer networking"])
    assert len(embs) == 2
    assert len(embs[0]) == 768
    assert len(embs[1]) == 768
    # Test unit norm (approx 1.0)
    norm = float(np.linalg.norm(np.array(embs[0])))
    assert abs(norm - 1.0) < 0.01


def test_rag_index_and_hybrid_search(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    s.ensure_dirs()
    engine = make_engine(s.db_path)
    emb_engine = EmbeddingEngine(s)

    with DBSession(engine) as db:
        course = Course(name="IT 222 Networking")
        db.add(course)
        db.commit()
        db.refresh(course)

        session = Session(title="CIDR Subnetting", course_id=course.id, consent_confirmed=True)
        db.add(session)
        db.commit()
        db.refresh(session)
        sid = session.id

        db.add(Segment(session_id=sid, source="them", t0=0.0, t1=20.0, text="Today we discuss CIDR and subnet masks."))
        db.add(Segment(session_id=sid, source="them", t0=25.0, t1=45.0, text="A /24 network has 256 addresses."))
        db.commit()

    count = index_session_chunks(sid, engine, emb_engine)
    assert count >= 1

    searcher = HybridRAGSearcher(engine, emb_engine)
    results = searcher.search("CIDR subnet mask", top_k=3)
    assert len(results) >= 1
    top = results[0]
    assert "CIDR" in top.text
    assert top.course_name == "IT 222 Networking"
    assert top.session_title == "CIDR Subnetting"

    # Test question answering
    answer = searcher.answer_question("What is CIDR?", router=FakeRouterForRAG())
    assert "Subnetting" in answer.answer
    assert len(answer.citations) >= 1
    assert answer.citations[0].course_name == "IT 222 Networking"
    assert answer.citations[0].timestamp_label == "00:00"


def test_phase3_api_endpoints(tmp_path):
    s = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", _env_file=None)
    s.ensure_dirs()
    from conftest import FakeCapture

    comps = Components(
        load_stt=lambda _s: FakeSTT(),
        capture_factory=lambda _s: lambda _clock: FakeCapture([]),
        vad_factory=EnergyVAD,
        list_devices=lambda: [],
        router_factory=lambda _s: FakeRouterForRAG(),
    )

    with TestClient(create_app(s, comps)) as client:
        token = client.app.state.api_token
        auth = {"Authorization": f"Bearer {token}"}

        # Create session with segment and index it
        with DBSession(client.app.state.engine) as db:
            course = Course(name="IT 311 Web Systems")
            db.add(course)
            db.commit()
            db.refresh(course)

            session = Session(title="FastAPI Architecture", course_id=course.id, consent_confirmed=True)
            db.add(session)
            db.commit()
            db.refresh(session)
            sid = session.id

            db.add(Segment(session_id=sid, source="them", t0=0.0, t1=15.0, text="FastAPI uses Pydantic for request validation."))
            db.add(Task(title="Complete FastAPI Assignment", status="todo", course_name="IT 311 Web Systems"))
            db.commit()

        # 1. Index session
        r_idx = client.post(f"/api/sessions/{sid}/index", headers=auth)
        assert r_idx.status_code == 200
        assert r_idx.json()["chunks_indexed"] >= 1

        # 2. Stats endpoint
        r_stats = client.get("/api/stats", headers=auth)
        assert r_stats.status_code == 200
        stats = r_stats.json()
        assert stats["total_sessions"] >= 1
        assert stats["total_tasks"] >= 1

        # 3. Search endpoint
        r_search = client.get("/api/chat/search?q=FastAPI", headers=auth)
        assert r_search.status_code == 200
        chunks = r_search.json()
        assert len(chunks) >= 1
        assert "FastAPI" in chunks[0]["text"]

        # 4. Chat endpoint
        r_chat = client.post("/api/chat", json={"query": "How does FastAPI validate requests?"}, headers=auth)
        assert r_chat.status_code == 200
        chat_data = r_chat.json()
        assert "Subnetting" in chat_data["answer"] or "FastAPI" in chat_data["answer"]
        assert len(chat_data["citations"]) >= 1
