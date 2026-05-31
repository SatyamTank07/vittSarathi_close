"""
RAG Pipeline for Financial Report Processing.

A standalone 5-layer RAG system for ingesting, indexing, and querying
Indian annual/quarterly financial reports (PDF).

Layers:
    1. Ingestion  — Sarvam Vision → Normalize → Classify → Chunk → Embed
    2. Storage    — pgvector + PageIndex tree + RefLinks
    3. Metadata   — Rich schema on every chunk
    4. Routing    — LLM-based 4-tier query classifier
    5. Retrieval  — Hybrid BM25+Dense → Rerank → Assemble Context
"""
