import os
import uuid
import logging
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import PyPDF2
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from src.core.database.connection import get_db, SessionLocal
from src.rag.config import TEMP_DIR
from src.rag.models.database import RAGDocument
from src.rag.models.schemas import IngestionRequest
from src.rag.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger("vittsarathi.api.document_routes")

router = APIRouter(prefix="/api/documents", tags=["documents"])

class DocumentMetadataOutput(BaseModel):
    company_id: str = Field(description="The ticker or short name of the company (e.g. TATA_MOTORS)")
    fiscal_year: int = Field(description="The 4 digit fiscal year of the report (e.g. 2024)")
    report_type: str = Field(description="Must be exactly 'annual' or 'quarterly'")
    fiscal_quarter: str | None = Field(None, description="Q1, Q2, Q3, Q4 or None if annual")

def extract_metadata_from_text(text: str) -> DocumentMetadataOutput:
    """Uses LLM to extract metadata from cover page text."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(DocumentMetadataOutput)
    prompt = PromptTemplate.from_template(
        "Extract the company identifier, fiscal year, and report type from this cover page text:\n\n{text}"
    )
    chain = prompt | llm
    return chain.invoke({"text": text})

async def run_pipeline_background(pdf_path: str, meta: DocumentMetadataOutput, document_id: str):
    """Background task to run the heavy ingestion pipeline."""
    # We create a new DB session for the background task
    db = SessionLocal()
    try:
        pipeline = IngestionPipeline(db)
        request = IngestionRequest(
            pdf_path=pdf_path,
            company_id=meta.company_id,
            report_type=meta.report_type, # type: ignore
            fiscal_year=meta.fiscal_year,
            fiscal_quarter=meta.fiscal_quarter
        )
        
        # The pipeline handles deduplication checking and RAGDocument updates.
        # But since we already created a pending RAGDocument, we might need to let pipeline handle it 
        # or we update the existing one. Wait, IngestionPipeline checks file_hash and creates RAGDocument.
        # It's better to let IngestionPipeline do the creation, so we don't have conflicting DB records.
        # We will let the pipeline run its normal course.
        
        status = await pipeline.ingest(request)
        logger.info(f"Background ingestion completed with status: {status.status}")
        
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}")
        # IngestionPipeline handles its own failure state updates
    finally:
        db.close()

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a PDF document. Extracts metadata automatically from the cover page 
    and kicks off the heavy ingestion pipeline in the background.
    """
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    # Save file to TEMP_DIR
    file_id = str(uuid.uuid4())
    temp_path = TEMP_DIR / f"{file_id}_{file.filename}"
    
    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # Extract text from first 2 pages
        cover_text = ""
        with open(temp_path, "rb") as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            for i in range(min(2, len(reader.pages))):
                page = reader.pages[i]
                cover_text += page.extract_text() or ""
                
        if not cover_text.strip():
            raise HTTPException(status_code=400, detail="Could not read cover page text for metadata extraction.")
            
        # Extract Metadata via LLM
        meta = extract_metadata_from_text(cover_text)
        
        # Start background task
        background_tasks.add_task(run_pipeline_background, str(temp_path), meta, file_id)
        
        return {
            "message": "Upload successful. Ingestion started in background.",
            "extracted_metadata": meta.model_dump(),
            "tracking_id": file_id # Used to poll if we adapt the status endpoint to look up by hash/file later
        }
        
    except Exception as e:
        # Cleanup on failure
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/{document_id}/status")
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    """Check the ingestion status of a document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
        
    doc = db.query(RAGDocument).filter(RAGDocument.id == doc_uuid).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return {
        "document_id": str(doc.id),
        "status": doc.ingestion_status,
        "company_id": doc.company_id,
        "fiscal_year": doc.fiscal_year,
        "error_message": doc.error_message
    }
