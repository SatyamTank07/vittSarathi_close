from sqlalchemy import Column, String, DateTime, Text
import uuid
from datetime import datetime, timezone
from src.core.database.connection import Base


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


class ChatSession(Base):
    """
    Persists session state between frontend requests.
    One row per active session. Updated on every dashboard response.
    Enables chat mode to read prior analysis without re-running agents.
    """
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, index=True,
                default=lambda: str(uuid.uuid4()))
    ticker = Column(String, nullable=True, index=True)
    company_name = Column(String, nullable=True)
    has_dashboard = Column(String, default="false")   # "true" | "false" as string
                                                       # avoids bool dialect issues
    shared_state_json = Column(Text, default="{}")    # full SharedState snapshot
    last_query = Column(Text, default="")
    analysis_report_id = Column(String, nullable=True)  # FK to analysis_reports.id
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
