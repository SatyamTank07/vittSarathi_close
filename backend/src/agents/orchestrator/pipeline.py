import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from src.agents.orchestrator.agent import orchestrator
from src.agents.quantitative.agent import quantitative_agent
from src.agents.qualitative.agent import qualitative_agent
from src.agents.risk_and_governance.agent import risk_agent
from src.agents.synthesizer.agent import synthesizer
from src.agents.base.shared_state import SharedState

logger = logging.getLogger("vittsarathi.pipeline")

async def run_analysis(user_query: str) -> dict:
    logger.info(f"[pipeline] ===== Starting analysis for query: {user_query} =====")
    start_time = datetime.now(timezone.utc)

    # ─── Step 1: Orchestrator ───
    logger.info("[pipeline] Step 1: Orchestrator — extracting entity & routing")
    state = await orchestrator.execute(user_query=user_query)
    logger.info(f"[pipeline] Orchestrator done. Company: {state.company_name}, Industry: {state.industry}")

    # ─── Step 2: Parallel Sub-Agents ───
    logger.info("[pipeline] Step 2: Running routed agents in PARALLEL")

    quant_state_copy = state.model_copy(deep=True)
    qual_state_copy = state.model_copy(deep=True)
    risk_state_copy = state.model_copy(deep=True)

    tasks = []
    agent_map = []

    if state.task_allocations.agent_2_quantitative.should_run:
        tasks.append(quantitative_agent.execute(quant_state_copy))
        agent_map.append("quantitative")
    
    if state.task_allocations.agent_3_qualitative.should_run:
        tasks.append(qualitative_agent.execute(qual_state_copy))
        agent_map.append("qualitative")
        
    if state.task_allocations.agent_4_risk_governance.should_run:
        tasks.append(risk_agent.execute(risk_state_copy))
        agent_map.append("risk_governance")

    if tasks:
        results = await asyncio.gather(*tasks)
        for i, result_state in enumerate(results):
            agent_name = agent_map[i]
            if agent_name == "quantitative":
                state.quantitative = result_state.quantitative
            elif agent_name == "qualitative":
                state.qualitative = result_state.qualitative
            elif agent_name == "risk_governance":
                state.risk_governance = result_state.risk_governance
                
            state.agent_statuses[agent_name] = result_state.agent_statuses.get(agent_name, "completed")
    
    logger.info(f"[pipeline] Routed sub-agents completed: {agent_map}")

    # ─── Step 3: Synthesizer ───
    logger.info("[pipeline] Step 3: Synthesizer — cross-referencing & compiling final thesis")
    state = await synthesizer.execute(state)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"[pipeline] ===== Analysis complete for {state.ticker} in {elapsed:.1f}s =====")
    
    if state.synthesis and state.synthesis.targeted_answer:
        logger.info(f"[pipeline] Verdict: Targeted Answer generated")
    else:
        logger.info(f"[pipeline] Verdict: {state.investment_verdict} (Confidence: {state.confidence_level})")

    result = {
        "user_query": state.user_query,
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
    from src.core.database.models import AnalysisReport

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
