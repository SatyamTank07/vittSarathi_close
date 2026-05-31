from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from src.core.database.connection import get_db
from src.core.database import models

router = APIRouter(prefix="/api")

@router.get("/reports")
def get_reports(db: Session = Depends(get_db)):
    """List all past analysis reports (most recent first)."""
    reports = db.query(models.AnalysisReport).order_by(
        models.AnalysisReport.created_at.desc()
    ).all()

    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "company_name": r.company_name,
            "sector": r.sector,
            "industry": r.industry,
            "investment_verdict": r.investment_verdict,
            "confidence_level": r.confidence_level,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific analysis report by ID."""
    report = db.query(models.AnalysisReport).filter(
        models.AnalysisReport.id == report_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": report.id,
        "ticker": report.ticker,
        "company_name": report.company_name,
        "sector": report.sector,
        "industry": report.industry,
        "investment_verdict": report.investment_verdict,
        "confidence_level": report.confidence_level,
        "report_markdown": report.report_markdown,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db)):
    """Delete a specific analysis report."""
    report = db.query(models.AnalysisReport).filter(
        models.AnalysisReport.id == report_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    db.delete(report)
    db.commit()
    return {"message": "Report deleted successfully"}
