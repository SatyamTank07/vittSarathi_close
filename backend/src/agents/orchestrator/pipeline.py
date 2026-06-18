import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from src.agents.orchestrator.agent import orchestrator
from src.agents.quantitative.agent import quantitative_agent
from src.agents.qualitative.agent import qualitative_agent
from src.agents.risk_and_governance.agent import risk_agent
from src.agents.sentiment_and_macro_analyst.agent import sentiment_and_macro_agent
from src.agents.synthesizer.agent import synthesizer
from src.agents.base.shared_state import SharedState, AgentResult, ResponseType
from typing import Callable, Awaitable
from pydantic import ValidationError
from src.agents.agent_registry import AGENT_REGISTRY, get_agent_names, get_sub_agent_names

logger = logging.getLogger("vittsarathi.pipeline")

# ─────────────────────────────────────────────
# TIMEOUTS per agent (seconds)
# Quant does heavy RAG so gets more time.
# Sentiment is just RSS + API so gets less.
# ─────────────────────────────────────────────

AGENT_TIMEOUTS = {
    "quantitative":    60,
    "qualitative":     45,
    "risk_governance": 45,
    "sentiment":       20,
}

DEFAULT_TIMEOUT = 45


# ─────────────────────────────────────────────
# FIELD MAP
# Maps agent name → which field on SharedState
# to write the AgentResult into.
# ─────────────────────────────────────────────

AGENT_RESULT_FIELD = {
    "quantitative":    "quantitative_result",
    "qualitative":     "qualitative_result",
    "risk_governance": "risk_governance_result",
    "sentiment":       "sentiment_result",
}


# ─────────────────────────────────────────────
# ERROR BOUNDARY
# Every agent call goes through this wrapper.
# It catches every failure mode and returns
# a clean AgentResult regardless of what broke.
# ─────────────────────────────────────────────

async def run_agent_safe(
    agent_fn: Callable[[SharedState], Awaitable],
    state: SharedState,
    agent_name: str,
) -> AgentResult:
    """
    Wraps a single agent coroutine in a full error boundary.

    Never raises. Always returns AgentResult.
    Handles: timeout, pydantic validation failure,
             MCP connection failure, and generic exceptions.
    """
    timeout = AGENT_TIMEOUTS.get(agent_name, DEFAULT_TIMEOUT)

    try:
        result = await asyncio.wait_for(
            agent_fn(state),
            timeout=timeout
        )
        return AgentResult(
            data=result,
            status="success",
            error=None,
            data_quality="high",
            fallback_used=False,
            agent_name=agent_name,
        )

    except asyncio.TimeoutError:
        msg = f"{agent_name} timed out after {timeout}s"
        logger.warning(msg)
        return AgentResult(
            data=None,
            status="failed",
            error=msg,
            data_quality="unavailable",
            fallback_used=False,
            agent_name=agent_name,
        )

    except ValidationError as e:
        # Agent ran but returned malformed output.
        # Log and mark as partial — synthesizer will caveat.
        msg = f"{agent_name} output failed Pydantic validation: {str(e)}"
        logger.error(msg)
        return AgentResult(
            data=None,
            status="partial",
            error=msg,
            data_quality="low",
            fallback_used=False,
            agent_name=agent_name,
        )

    except ConnectionError as e:
        # MCP server unreachable.
        # In Step 6, agents will have a skip_mcp fallback.
        # For now, mark as failed.
        msg = f"{agent_name} MCP connection failed: {str(e)}"
        logger.error(msg)
        return AgentResult(
            data=None,
            status="failed",
            error=msg,
            data_quality="unavailable",
            fallback_used=True,
            agent_name=agent_name,
        )

    except Exception as e:
        msg = f"{agent_name} failed with unexpected error: {type(e).__name__}: {str(e)}"
        logger.error(msg, exc_info=True)
        return AgentResult(
            data=None,
            status="failed",
            error=msg,
            data_quality="unavailable",
            fallback_used=False,
            agent_name=agent_name,
        )


# ─────────────────────────────────────────────
# EXECUTION PLAN VALIDATOR
# Before building the gather list, validate
# that the plan only references known agents
# and known sub-agents. Catch bad LLM output
# before it hits the pipeline.
# ─────────────────────────────────────────────

def validate_execution_plan(state: SharedState) -> list[str]:
    """
    Returns a list of warning strings for any unknown
    agent or sub-agent names in the execution plan.
    Does not raise — warnings are logged, unknowns are skipped.
    """
    warnings = []
    valid_agent_names = get_agent_names()

    for agent_name, agent_exec in state.execution_plan.agents.items():

        # Unknown primary agent
        if agent_name not in valid_agent_names:
            warnings.append(
                f"ExecutionPlan references unknown agent '{agent_name}'. Skipping."
            )
            continue

        # Unknown sub-agents
        valid_subs = get_sub_agent_names(agent_name)
        for sub_name in agent_exec.sub_agents:
            if sub_name not in valid_subs:
                warnings.append(
                    f"ExecutionPlan references unknown sub-agent "
                    f"'{sub_name}' under '{agent_name}'. Skipping."
                )

    return warnings


# ─────────────────────────────────────────────
# DYNAMIC GATHER BUILDER
# Reads execution_plan.agents, checks should_run,
# instantiates agents from AGENT_REGISTRY,
# passes approved sub-agents to each.
# ─────────────────────────────────────────────

def build_task_list(state: SharedState) -> list:
    tasks = []

    for agent_name, agent_exec in state.execution_plan.agents.items():
        if not agent_exec.should_run:
            logger.info(f"[pipeline] Skipping {agent_name} — should_run=False")
            continue

        registry_entry = AGENT_REGISTRY.get(agent_name)
        if not registry_entry:
            logger.warning(f"[pipeline] '{agent_name}' not in AGENT_REGISTRY, skipping")
            continue

        agent_cls = registry_entry.agent_class
        sub_registry = registry_entry.sub_agents

        # Only pass sub-agents the Orchestrator approved
        approved_sub_agents = {
            name: sub.agent_class
            for name, sub in sub_registry.items()
            if name in agent_exec.sub_agents
        }

        if approved_sub_agents:
            logger.info(
                f"[pipeline] {agent_name} will run with "
                f"sub-agents: {list(approved_sub_agents.keys())}"
            )

        # Instantiate with approved sub-agents
        instance = agent_cls(sub_agents=approved_sub_agents)
        tasks.append((agent_name, instance.execute))

    return tasks

# ─────────────────────────────────────────────
# MAIN PIPELINE ENTRY POINT
# ─────────────────────────────────────────────

async def run_pipeline(state: SharedState) -> SharedState:
    """
    Main pipeline executor.

    Flow:
      1. Guard: execution_plan must exist
      2. Validate the plan against the registry
      3. Build dynamic task list
      4. Run with asyncio.gather — each wrapped in run_agent_safe
      5. Write results back to SharedState
      6. Pass to Synthesizer
    """
    response_type = state.execution_plan.response_type
    agents_running = [
        k for k, v in state.execution_plan.agents.items() if v.should_run
    ]
    skipped_agents = [
        k for k, v in state.execution_plan.agents.items() if not v.should_run
    ]
    logger.info(
        f"[pipeline] response_type={response_type} | "
        f"running={agents_running} | "
        f"skipped={skipped_agents}"
    )

    # ── Guard ──
    if state.execution_plan is None:
        raise ValueError(
            "run_pipeline called with no execution_plan in SharedState. "
            "Orchestrator must run first."
        )

    # ── Validate plan ──
    warnings = validate_execution_plan(state)
    for w in warnings:
        logger.warning(w)

    # ── Build task list ──
    tasks = build_task_list(state)

    if not tasks:
        logger.info(
            f"No agents to run for response_type="
            f"{state.execution_plan.response_type}. "
            f"Proceeding directly to Synthesizer."
        )
    else:
        logger.info(
            f"Running {len(tasks)} agent(s): "
            f"{[name for name, _ in tasks]}"
        )

    # ── Dynamic gather ──
    # return_exceptions=False because run_agent_safe never raises
    results: list[AgentResult] = await asyncio.gather(
        *[
            run_agent_safe(agent_fn, state, agent_name)
            for agent_name, agent_fn in tasks
        ]
    )

    # ── Write results back to SharedState ──
    for agent_result in results:
        field_name = AGENT_RESULT_FIELD.get(agent_result.agent_name)
        if field_name:
            setattr(state, field_name, agent_result)
            state.agent_statuses[agent_result.agent_name] = agent_result.status
            logger.info(
                f"{agent_result.agent_name} → "
                f"status={agent_result.status}, "
                f"quality={agent_result.data_quality}"
            )

    # ── Synthesizer ──
    # Synthesizer always runs regardless of how many agents ran.
    # It reads agent_statuses to know what data is available.
    state = await run_synthesizer(state)

    return state


async def run_synthesizer(state: SharedState) -> SharedState:
    """
    Calls the Synthesizer agent.
    Synthesizer always runs — for chat mode it just answers one question,
    for dashboard mode it builds the full thesis.
    Step 9 will update the Synthesizer's internal prompt logic.
    For now it runs exactly as it did before.
    """
    from src.agents.synthesizer.agent import synthesizer

    try:
        synthesis_result = await asyncio.wait_for(
            synthesizer.execute(state),
            timeout=60
        )
        state = synthesis_result
        state.agent_statuses["synthesizer"] = "success"

    except Exception as e:
        logger.error(f"Synthesizer failed: {e}", exc_info=True)
        state.agent_statuses["synthesizer"] = "failed"

    return state

def _build_result(state: SharedState, response_type: ResponseType, start_time: datetime) -> dict:
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    return {
        "status": "success",
        "response_type": response_type.value,
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
        "sentiment": state.sentiment.model_dump() if state.sentiment else None,
        "agent_statuses": state.agent_statuses,
        "ui_manifest": state.ui_manifest.model_dump() if state.ui_manifest else None,
        "analysis_duration_seconds": round(elapsed, 1),
        "shared_state_json": state.model_dump_json(),
    }

async def run_analysis(user_query: str) -> dict:
    logger.info(f"[pipeline] ===== Starting analysis for query: {user_query} =====")
    start_time = datetime.now(timezone.utc)

    # ─── Step 1: Orchestrator ───
    logger.info("[pipeline] Step 1: Orchestrator — extracting entity & routing")
    state = await orchestrator.execute(user_query=user_query)
    logger.info(f"[pipeline] Orchestrator done. Company: {state.company_name}, Industry: {state.industry}")

    if state.clarification_needed:
        logger.info("[pipeline] Ambiguous entity detected. Halting pipeline for user clarification.")
        candidates = getattr(state, "disambiguation_candidates", [])
        candidates_str = "\n".join([
            f"- **{c.get('company_name', 'Unknown')}** ({c.get('ticker', '')})"
            for c in candidates
        ])
        
        msg = (
            f"I found multiple matches for your query. "
            f"Could you please clarify which one you meant?\n\n{candidates_str}"
        )
        state.final_thesis = msg
        state.investment_verdict = "Clarification Needed"
        
        result = {
            "status": "clarification_needed",
            "response_type": getattr(state.execution_plan, "response_type", ResponseType.DASHBOARD).value if state.execution_plan else "dashboard",
            "candidates": candidates,
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
            "quantitative": None,
            "qualitative": None,
            "risk_governance": None,
            "sentiment": None,
            "agent_statuses": state.agent_statuses,
            "analysis_duration_seconds": round((datetime.now(timezone.utc) - start_time).total_seconds(), 1),
            "shared_state_json": state.model_dump_json(),
        }
        return result

    # ─── Step 2: Dynamic Agent Pipeline ───
    response_type = state.execution_plan.response_type
    
    if response_type == ResponseType.CHAT:
        if not state.has_existing_dashboard:
            logger.warning(
                "[pipeline] CHAT requested but no existing dashboard. "
                "Falling back to dashboard mode."
            )
            state = await run_pipeline(state)
        else:
            logger.info(
                f"[pipeline] CHAT mode — skipping all agents. "
                f"Synthesizer will answer from existing state. "
                f"Full chat context wired in Step 9."
            )
            state = await run_synthesizer(state)
            
    elif response_type == ResponseType.PATCH:
        logger.info(f"[pipeline] PATCH mode — running partial pipeline.")
        state = await run_pipeline(state)
        
    else:  # DASHBOARD
        state = await run_pipeline(state)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"[pipeline] ===== Analysis complete for {state.ticker} in {elapsed:.1f}s =====")
    
    if state.synthesis and state.synthesis.targeted_answer:
        logger.info(f"[pipeline] Verdict: Targeted Answer generated")
    else:
        logger.info(f"[pipeline] Verdict: {state.investment_verdict} (Confidence: {state.confidence_level})")

    return _build_result(state, response_type, start_time)

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
