from sqlalchemy import Column, String, DateTime, Text
import uuid
from datetime import datetime, timezone
from app.database import Base


class AnalysisReport(Base):
    """Stores completed multi-agent analysis reports."""
    __tablename__ = "analysis_reports"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    ticker = Column(String, index=True)
    company_name = Column(String)
    sector = Column(String, default="")
    industry = Column(String, default="")
    investment_verdict = Column(String, default="Neutral")      # Bullish / Neutral / Bearish
    confidence_level = Column(String, default="Low")             # High / Medium / Low
    report_markdown = Column(Text, default="")                   # The final thesis in Markdown
    shared_state_json = Column(Text, default="{}")               # Full JSON for debugging/replay
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
