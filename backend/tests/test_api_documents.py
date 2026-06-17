import pytest
import uuid
import os
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.api.main import app
from src.core.database.connection import get_db, Base, engine
from src.rag.models.database import RAGDocument
from src.api.routes.document_routes import DocumentMetadataOutput
from sqlalchemy.orm import sessionmaker

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(RAGDocument).delete()
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)

@patch("src.api.routes.document_routes.extract_metadata_from_text")
@patch("src.api.routes.document_routes.PyPDF2.PdfReader")
def test_upload_document_success(mock_pdf_reader, mock_extract_meta):
    """Test successful document upload triggers background ingestion."""
    mock_extract_meta.return_value = DocumentMetadataOutput(
        company_id="TCS",
        fiscal_year=2024,
        report_type="annual",
        fiscal_quarter=None
    )
    
    mock_instance = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Dummy cover text"
    # Using a list so len() works on pages
    mock_instance.pages = [mock_page]
    mock_pdf_reader.return_value = mock_instance
    
    # Create a dummy PDF file content in memory
    file_content = b"%PDF-1.4 dummy content"
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("dummy.pdf", file_content, "application/pdf")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "upload successful" in data["message"].lower()
    assert data["extracted_metadata"]["company_id"] == "TCS"
    assert "tracking_id" in data

def test_upload_document_invalid_extension():
    """Test uploading a non-PDF file returns 400."""
    response = client.post(
        "/api/documents/upload",
        files={"file": ("dummy.txt", b"hello world", "text/plain")}
    )
    
    assert response.status_code == 400
    assert "only pdf files are supported" in response.json()["detail"].lower()

def test_get_document_status():
    """Test retrieving ingestion status of a document."""
    doc_id = uuid.uuid4()
    db = TestingSessionLocal()
    doc = RAGDocument(
        id=doc_id,
        file_hash="fake-hash",
        company_id="AAPL",
        fiscal_year=2023,
        report_type="quarterly",
        fiscal_quarter="Q1",
        ingestion_status="processing"
    )
    db.add(doc)
    db.commit()
    db.close()
    
    response = client.get(f"/api/documents/{str(doc_id)}/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc_id)
    assert data["status"] == "processing"
    assert data["company_id"] == "AAPL"

def test_get_document_status_not_found():
    """Test retrieving status for a non-existent document ID."""
    response = client.get(f"/api/documents/{str(uuid.uuid4())}/status")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"

def test_get_document_status_invalid_uuid():
    """Test retrieving status with invalid UUID format."""
    response = client.get("/api/documents/invalid-uuid/status")
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid document ID format"
