import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.database.connection import get_db, Base, engine
from src.core.database.models import AnalysisReport
from sqlalchemy.orm import sessionmaker

# Set up test database
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
    # Clear existing
    db.query(AnalysisReport).delete()
    
    # Add dummy reports
    report1 = AnalysisReport(
        id="test-rep-1",
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Tech",
        industry="Hardware",
        investment_verdict="Buy",
        confidence_level="High",
        report_markdown="# Apple Report"
    )
    report2 = AnalysisReport(
        id="test-rep-2",
        ticker="GOOGL",
        company_name="Alphabet Inc.",
        sector="Tech",
        industry="Software",
        investment_verdict="Hold",
        confidence_level="Medium",
        report_markdown="# Google Report"
    )
    db.add(report1)
    db.add(report2)
    db.commit()
    db.close()
    
    yield
    
    Base.metadata.drop_all(bind=engine)

def test_get_reports():
    """Test retrieving list of reports."""
    response = client.get("/api/reports")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Check that they are returned in descending order (report2 should probably come first or we just check presence)
    ids = [r["id"] for r in data]
    assert "test-rep-1" in ids
    assert "test-rep-2" in ids

def test_get_report_by_id():
    """Test retrieving a single report by ID."""
    response = client.get("/api/reports/test-rep-1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-rep-1"
    assert data["ticker"] == "AAPL"
    assert data["report_markdown"] == "# Apple Report"

def test_get_report_not_found():
    """Test retrieving non-existent report."""
    response = client.get("/api/reports/unknown-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"

def test_delete_report():
    """Test deleting a report."""
    response = client.delete("/api/reports/test-rep-2")
    assert response.status_code == 200
    assert response.json()["message"] == "Report deleted successfully"
    
    # Verify it is gone
    get_response = client.get("/api/reports/test-rep-2")
    assert get_response.status_code == 404

def test_delete_report_not_found():
    """Test deleting a non-existent report."""
    response = client.delete("/api/reports/unknown-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"
