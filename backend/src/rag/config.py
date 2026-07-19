"""
RAG Pipeline Configuration.

All RAG-specific settings loaded from environment variables.
Uses the existing OPENAI_API_KEY from the project's .env file.
"""

import os
from pathlib import Path


# ──────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────
RAG_ROOT = Path(__file__).parent
PROMPTS_DIR = RAG_ROOT / "prompts"

# Temporary directory for PDF batch splitting (inside project)
TEMP_DIR = RAG_ROOT / ".tmp"
TEMP_DIR.mkdir(exist_ok=True)

# Directory to store raw Sarvam JSON output for debugging
RAW_OUTPUT_DIR = RAG_ROOT / "raw_sarvam_outputs"
RAW_OUTPUT_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────
# Sarvam Vision API
# ──────────────────────────────────────────────────────────────
SARVAM_API_KEY: str = os.environ.get("SARVAM_API_KEY", "")
SARVAM_BASE_URL: str = "https://api.sarvam.ai"
SARVAM_LANGUAGE: str = "en-IN"
SARVAM_OUTPUT_FORMAT: str = "html"  # Best for table preservation
SARVAM_MAX_PAGES_PER_JOB: int = 10
SARVAM_POLL_INTERVAL: int = 5       # seconds between status polls
SARVAM_POLL_TIMEOUT: int = 300      # max seconds to wait for a job


# ──────────────────────────────────────────────────────────────
# OpenAI (reuse from existing .env)
# ──────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"
EMBEDDING_DIMENSIONS: int = 1536
EMBEDDING_BATCH_SIZE: int = 100     # OpenAI batch limit
CLASSIFIER_MODEL: str = "gpt-4o-mini"
CLASSIFIER_TEMPERATURE: float = 0.1
CLASSIFIER_MAX_TOKENS: int = 500


# ──────────────────────────────────────────────────────────────
# Cohere Reranker
# ──────────────────────────────────────────────────────────────
COHERE_API_KEY: str = os.environ.get("COHERE_API_KEY", "")
COHERE_RERANK_MODEL: str = "rerank-english-v3.0"
RERANKER_TOP_K: int = 10


# ──────────────────────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────────────────────
CHUNK_SIZE: int = 512               # tokens
CHUNK_OVERLAP: int = 64             # tokens


# ──────────────────────────────────────────────────────────────
# Retrieval
# ──────────────────────────────────────────────────────────────
RRF_K: int = 60                     # Reciprocal Rank Fusion constant
HYBRID_RETRIEVAL_TOP_K: int = 50    # Candidates from each retriever
FINAL_TOP_K: int = 10               # After reranking


# ──────────────────────────────────────────────────────────────
# Section Type Taxonomy
# ──────────────────────────────────────────────────────────────
SECTION_TYPES: list[str] = [
    "balance_sheet",
    "profit_loss",
    "cash_flow",
    "schedule",
    "note_to_accounts",
    "directors_report",
    "mda",                            # Management Discussion & Analysis
    "auditors_report",
    "management_profile",
    "vision_mission",
    "risk_factors",
    "shareholders_info",
    "corporate_governance",
    "standalone_financials",
    "consolidated_financials",
    "other",
]

# Section types that contain structured/tabular data → go to PageIndex
STRUCTURED_SECTION_TYPES: list[str] = [
    "balance_sheet",
    "profit_loss",
    "cash_flow",
    "schedule",
    "note_to_accounts",
    "standalone_financials",
    "consolidated_financials",
]

# Section types that contain narrative text → go to vector store
NARRATIVE_SECTION_TYPES: list[str] = [
    "directors_report",
    "mda",
    "auditors_report",
    "management_profile",
    "vision_mission",
    "risk_factors",
    "shareholders_info",
    "corporate_governance",
    "other",
]


# ──────────────────────────────────────────────────────────────
# Database (reuse the existing connection string)
# ──────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/vittsarathi_chat"
)


def validate_config() -> list[str]:
    """
    Check that required environment variables are set.
    Returns a list of missing/invalid config keys.
    """
    issues: list[str] = []

    if not SARVAM_API_KEY:
        issues.append("SARVAM_API_KEY is not set")
    if not OPENAI_API_KEY:
        issues.append("OPENAI_API_KEY is not set")
    if not COHERE_API_KEY:
        issues.append("COHERE_API_KEY is not set")

    return issues
