"""Retrieval-Augmented Generation (RAG) module for E.V.E. lecture knowledge."""

from eve.rag.embeddings import EmbeddingEngine
from eve.rag.index import index_session_chunks, init_rag_tables
from eve.rag.chat import HybridRAGSearcher, RAGAnswer, Citation

__all__ = [
    "EmbeddingEngine",
    "init_rag_tables",
    "index_session_chunks",
    "HybridRAGSearcher",
    "RAGAnswer",
    "Citation",
]
