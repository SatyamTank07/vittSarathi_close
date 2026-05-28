"""
Pipeline — The orchestration engine that ties all agents together.

Flow:
1. Orchestrator fetches data, classifies industry, creates SharedState
2. Quantitative + Qualitative + Risk agents run IN PARALLEL
3. Synthesizer reads all outputs, resolves contradictions, produces final thesis
4. Report is saved to PostgreSQL
"""

import asyncio
import logging
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.orchestrator import orchestrator
from app.agents.quantitative_agent import quantitative_agent
from app.agents.qualitative_agent import qualitative_agent
from app.agents.risk_agent import risk_agent
from app.agents.synthesizer import synthesizer
from app.agents.shared_state import SharedState

logger = logging.getLogger("vittsarathi.pipeline")


async def run_analysis(ticker: str) -> dict:
    """
    Run the full multi-agent analysis pipeline.
    
    Args:
        ticker: Stock ticker symbol (e.g., "TCS", "RELIANCE.NS")
        
    Returns:
        Dict with the complete analysis result including final thesis,
        individual agent outputs, and metadata.
    """
    logger.info(f"[pipeline] ===== Starting analysis for {ticker} =====")
    start_time = datetime.now(timezone.utc)

    # ─── Step 1: Orchestrator ───
    logger.info("[pipeline] Step 1: Orchestrator — fetching data & classifying industry")
    state = await orchestrator.execute(ticker=ticker)
    logger.info(f"[pipeline] Orchestrator done. Company: {state.company_name}, Industry: {state.industry}")

    # ─── Step 2: Parallel Sub-Agents ───
    logger.info("[pipeline] Step 2: Running Quantitative + Qualitative + Risk agents in PARALLEL")

    # Deep copy the state for each agent so they don't interfere
    quant_state_copy = state.model_copy(deep=True)
    qual_state_copy = state.model_copy(deep=True)
    risk_state_copy = state.model_copy(deep=True)

    quant_result, qual_result, risk_result = await asyncio.gather(
        quantitative_agent.execute(quant_state_copy),
        qualitative_agent.execute(qual_state_copy),
        risk_agent.execute(risk_state_copy),
    )

    # Merge outputs back into the master state
    state.quantitative = quant_result.quantitative
    state.qualitative = qual_result.qualitative
    state.risk_governance = risk_result.risk_governance
    state.agent_statuses.update({
        "quantitative": quant_result.agent_statuses.get("quantitative", "completed"),
        "qualitative": qual_result.agent_statuses.get("qualitative", "completed"),
        "risk_governance": risk_result.agent_statuses.get("risk_governance", "completed"),
    })

    logger.info("[pipeline] All 3 sub-agents completed")

    # ─── Step 3: Synthesizer ───
    logger.info("[pipeline] Step 3: Synthesizer — cross-referencing & compiling final thesis")
    state = await synthesizer.execute(state)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"[pipeline] ===== Analysis complete for {ticker} in {elapsed:.1f}s =====")
    logger.info(f"[pipeline] Verdict: {state.investment_verdict} (Confidence: {state.confidence_level})")

    # ─── Build response ───
    result = {
        "ticker": state.ticker,
        "company_name": state.company_name,
        "sector": state.sector,
        "industry": state.industry,
        "currency": state.currency,
        "current_price": state.current_price,
        "investment_verdict": state.investment_verdict,
        "confidence_level": state.confidence_level,
        "final_thesis": state.final_thesis,
        "quantitative": state.quantitative.model_dump() if state.quantitative else None,
        "qualitative": state.qualitative.model_dump() if state.qualitative else None,
        "risk_governance": state.risk_governance.model_dump() if state.risk_governance else None,
        "agent_statuses": state.agent_statuses,
        "analysis_duration_seconds": round(elapsed, 1),
        "shared_state_json": state.model_dump_json(),
    }

    return result


def save_report_to_db(db: Session, result: dict) -> str:
    """
    Save the analysis result to the database.
    
    Returns the report ID.
    """
    from app.models import AnalysisReport

    report = AnalysisReport(
        ticker=result["ticker"],
        company_name=result["company_name"],
        sector=result.get("sector", ""),
        industry=result.get("industry", ""),
        investment_verdict=result.get("investment_verdict", "Neutral"),
        confidence_level=result.get("confidence_level", "Low"),
        report_markdown=result.get("final_thesis", ""),
        shared_state_json=result.get("shared_state_json", "{}"),
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(f"[pipeline] Report saved to DB with id={report.id}")
    return report.id
