"""
RAG Pipeline — Standalone Demo CLI

Use this script to test the RAG pipeline locally before integrating
it with the FastAPI application.

Usage:
    # 1. Initialize the database
    python run_demo.py init-db
    
    # 2. Ingest a PDF report
    python run_demo.py ingest /path/to/report.pdf --company RIL --year 2024 --type annual
    
    # 3. Query the system
    python run_demo.py query "What was the total revenue in 2024?"
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup basic logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

from src.rag.config import DATABASE_URL
from src.rag.models.database import init_rag_db
from src.rag.models.schemas import IngestionRequest, QueryRequest
from src.rag.ingestion.pipeline import IngestionPipeline
from src.rag.storage.vector_store import VectorStore
from src.rag.storage.pageindex import PageIndexStore
from src.rag.storage.document_store import DocumentStore
from src.rag.storage.ref_store import RefStore
from src.rag.retrieval.hybrid_retriever import HybridRetriever
from src.rag.retrieval.context_assembler import ContextAssembler

# Setup DB
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def cmd_init_db():
    """Initialize the RAG database tables and extensions."""
    print("Initializing RAG database schema...")
    try:
        init_rag_db(engine)
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        sys.exit(1)


async def cmd_ingest(pdf_path: str, company: str, year: int, report_type: str, quarter: str = None):
    """Run the ingestion pipeline on a PDF."""
    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
        
    print(f"Starting ingestion for {company} {year} {report_type}...")
    
    db = SessionLocal()
    try:
        pipeline = IngestionPipeline(db)
        request = IngestionRequest(
            pdf_path=pdf_path,
            company_id=company,
            report_type=report_type,
            fiscal_year=year,
            fiscal_quarter=quarter
        )
        
        status = await pipeline.ingest(request)
        
        if status.status == "completed":
            print(f"\n✅ Ingestion completed successfully!")
            print(f"Document ID: {status.document_id}")
            print(f"Pages processed: {status.pages_processed}/{status.total_pages}")
            print(f"Sections found: {status.sections_found}")
            print(f"Tables found: {status.tables_found}")
            print(f"Vector chunks: {status.chunks_created}")
        elif status.status == "already_exists":
            print(f"\n⚠️ Document already exists in DB (ID: {status.document_id}). Skipping.")
        else:
            print(f"\n❌ Ingestion failed: {status.errors}")
            
    finally:
        db.close()


async def cmd_query(query_text: str):
    """Run a query through the retrieval pipeline."""
    print(f"Querying: '{query_text}'\n")
    
    db = SessionLocal()
    try:
        # Initialize stores
        v_store = VectorStore(db)
        pi_store = PageIndexStore(db)
        d_store = DocumentStore(db)
        r_store = RefStore(db)
        
        # Initialize pipeline components
        retriever = HybridRetriever(v_store, pi_store)
        assembler = ContextAssembler(r_store, d_store)
        
        # Execute retrieval
        request = QueryRequest(query=query_text)
        raw_context = await retriever.retrieve(request)
        final_context = assembler.assemble(raw_context)
        
        # Display Results
        print("═" * 60)
        print(f"QUERY TIER : {final_context.query_tier.value}")
        print(f"STRATEGY   : {final_context.retrieval_strategy}")
        print(f"EST TOKENS : ~{final_context.total_tokens_estimate}")
        print(f"FILTERS    : {final_context.metadata_filters_applied}")
        print("═" * 60)
        
        print("\nTOP CHUNKS RETRIEVED:")
        for i, chunk in enumerate(final_context.chunks[:3]):  # Show top 3
            print(f"\n--- Rank {i+1} (Score: {chunk.score:.3f} via {chunk.score_source}) ---")
            print(f"Section: {chunk.metadata.section_type}")
            preview = chunk.chunk_text[:300].replace('\n', ' ')
            print(f"Content: {preview}{'...' if len(chunk.chunk_text) > 300 else ''}")
            
        if final_context.resolved_refs:
            print("\nRESOLVED FOOTNOTES:")
            for ref in final_context.resolved_refs:
                print(f"- {ref['ref_code']}: {ref['resolved_text'][:150]}...")
                
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VittSarathi RAG Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Init DB
    subparsers.add_parser("init-db", help="Initialize the database schema")
    
    # Ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a PDF report")
    ingest_parser.add_argument("pdf_path", help="Path to the PDF file")
    ingest_parser.add_argument("--company", required=True, help="Company ID (e.g., RIL, TCS)")
    ingest_parser.add_argument("--year", required=True, type=int, help="Fiscal Year (e.g., 2024)")
    ingest_parser.add_argument("--type", required=True, choices=["annual", "quarterly"], help="Report type")
    ingest_parser.add_argument("--quarter", help="Fiscal Quarter (e.g., Q1)")
    
    # Query
    query_parser = subparsers.add_parser("query", help="Query the RAG system")
    query_parser.add_argument("text", help="The query text")
    
    args = parser.parse_args()
    
    if args.command == "init-db":
        cmd_init_db()
    elif args.command == "ingest":
        asyncio.run(cmd_ingest(args.pdf_path, args.company, args.year, args.type, args.quarter))
    elif args.command == "query":
        asyncio.run(cmd_query(args.text))
