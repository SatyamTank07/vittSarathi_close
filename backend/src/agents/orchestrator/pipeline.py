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

def _build_clarification_message(candidates: list) -> str:
    """
    Builds the human-readable message shown in the chat panel
    when clarification is needed.
    """
    if not candidates:
        return (
            "I couldn't confidently identify which company you meant. "
            "Please provide a more specific name or ticker symbol."
        )

    lines = [
        "I found multiple matches for your query. "
        "Which company did you mean?\n"
    ]
    for c in candidates:
        name = c.get("company_name", "Unknown")
        ticker = c.get("ticker", "")
        lines.append(f"- **{name}** ({ticker})")

    return "\n".join(lines)

def _build_clarification_result(
    state: SharedState,
    start_time: datetime
) -> dict:
    """
    Returns a structured response when the Orchestrator
    could not confidently resolve the company entity.
    No agents have run at this point.
    """
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    return {
        "status": "clarification_needed",
        "response_type": (
            state.execution_plan.response_type.value
            if state.execution_plan
            else ResponseType.DASHBOARD.value
        ),
        "session_id": state.session_id,
        "user_query": state.user_query,
        "ticker": state.ticker,
        "company_name": state.company_name,
        "sector": state.sector,
        "industry": state.industry,
        "currency": state.currency,
        "current_price": state.current_price,
        "orchestrator_confidence": state.orchestrator_confidence,
        "candidates": state.disambiguation_candidates,
        "investment_verdict": "Clarification Needed",
        "confidence_level": "N/A",
        "final_thesis": _build_clarification_message(state.disambiguation_candidates),
        "quantitative": None,
        "qualitative": None,
        "risk_governance": None,
        "sentiment": None,
        "agent_statuses": state.agent_statuses,
        "ui_manifest": None,
        "state_patch": None,
        "analysis_duration_seconds": round(elapsed, 1),
        "shared_state_json": state.model_dump_json(),
    }

def _build_result(state: SharedState, response_type: ResponseType, start_time: datetime) -> dict:
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    return {
        "status": "success",
        "response_type": response_type.value,
        "session_id": state.session_id,
        "user_query": state.user_query,
        "ticker": state.ticker,
        "company_name": state.company_name,
        "sector": state.sector,
        "industry": state.industry,
        "currency": state.currency,
        "current_price": state.current_price,
        "orchestrator_confidence": state.orchestrator_confidence,
        "investment_verdict": state.investment_verdict,
        "confidence_level": state.confidence_level,
        "final_thesis": state.final_thesis,
        "quantitative": state.quantitative.model_dump() if state.quantitative else None,
        "qualitative": state.qualitative.model_dump() if state.qualitative else None,
        "risk_governance": state.risk_governance.model_dump() if state.risk_governance else None,
        "sentiment": state.sentiment.model_dump() if state.sentiment else None,
        "agent_statuses": state.agent_statuses,
        "ui_manifest": state.ui_manifest.model_dump() if state.ui_manifest else None,
        "state_patch": state.state_patch.model_dump() if state.state_patch else None,
        "analysis_duration_seconds": round(elapsed, 1),
        "shared_state_json": state.model_dump_json(),
    }

def _generate_state_hash(state: SharedState) -> str:
    """MD5 hash of the SharedState JSON. Used for stale state detection."""
    import hashlib
    return hashlib.md5(
        state.model_dump_json().encode("utf-8")
    ).hexdigest()


def _load_session(db: Session, session_id: str) -> SharedState | None:
    """
    Loads a prior SharedState from the ChatSession table.
    Returns None if session_id is not found or state is unparseable.
    """
    from src.core.database.models import ChatSession
    try:
        row = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if row is None:
            return None
        if row.has_dashboard != "true":
            return None
        state = SharedState.model_validate_json(row.shared_state_json)
        state.has_existing_dashboard = True
        return state
    except Exception as e:
        logger.warning(f"[pipeline] Failed to load session {session_id}: {e}")
        return None


def _save_session(db: Session, state: SharedState, report_id: str | None = None) -> str:
    """
    Saves or updates a ChatSession row.
    Returns the session_id.
    Called after every successful dashboard or patch response.
    """
    from src.core.database.models import ChatSession
    try:
        session_id = state.session_id

        existing = db.query(ChatSession).filter(
            ChatSession.id == session_id
        ).first()

        if existing:
            existing.shared_state_json = state.model_dump_json()
            existing.has_dashboard = "true"
            existing.ticker = state.ticker
            existing.company_name = state.company_name
            existing.last_query = state.user_query or ""
            if report_id:
                existing.analysis_report_id = report_id
            existing.updated_at = datetime.now(timezone.utc)
        else:
            row = ChatSession(
                id=session_id,
                ticker=state.ticker,
                company_name=state.company_name,
                has_dashboard="true",
                shared_state_json=state.model_dump_json(),
                last_query=state.user_query or "",
                analysis_report_id=report_id,
            )
            db.add(row)

        db.commit()
        return session_id

    except Exception as e:
        logger.error(f"[pipeline] Failed to save session: {e}")
        return state.session_id


def _check_state_hash(
    state: SharedState,
    existing_state_hash: str | None
) -> bool:
    """
    Returns True if the frontend's state hash matches the backend's.
    If False, the backend should return a full dashboard refresh
    instead of a patch — the frontend is out of sync.
    """
    if existing_state_hash is None:
        return True   # no hash sent — assume in sync
    current_hash = _generate_state_hash(state)
    return current_hash == existing_state_hash


async def run_analysis(
    user_query: str,
    session_id: str | None = None,
    existing_state_hash: str | None = None,
    db: Session | None = None,
) -> dict:
    import uuid as _uuid
    logger.info(f"[pipeline] ===== Starting analysis: '{user_query}' | session={session_id} =====")
    start_time = datetime.now(timezone.utc)

    # ── Session: try to load prior state ──────────────────────
    prior_state: SharedState | None = None
    if session_id and db:
        prior_state = _load_session(db, session_id)
        if prior_state:
            logger.info(
                f"[pipeline] Loaded prior session {session_id} "
                f"for {prior_state.company_name}"
            )

    # ── Assign or generate session_id ─────────────────────────
    # We generate it now so it can be written into SharedState
    # before the orchestrator runs — the orchestrator won't
    # overwrite session_id since it's not part of its output.
    resolved_session_id = session_id or str(_uuid.uuid4())

    # ─── Step 1: Orchestrator ─────────────────────────────────
    logger.info("[pipeline] Step 1: Orchestrator")
    state = await orchestrator.execute(user_query=user_query)
    state.session_id = resolved_session_id

    # ── Secondary confidence guard ────────────────────────────
    if state.clarification_needed and state.execution_plan:
        any_running = any(
            v.should_run for v in state.execution_plan.agents.values()
        )
        if any_running:
            logger.warning(
                "[pipeline] clarification_needed=True but should_run=True found. "
                "Forcing all agents off."
            )
            for agent_exec in state.execution_plan.agents.values():
                agent_exec.should_run = False

    logger.info(
        f"[pipeline] Orchestrator done. "
        f"Company={state.company_name}, Industry={state.industry}"
    )

    # ── Clarification short-circuit ───────────────────────────
    if state.clarification_needed:
        logger.warning(
            f"[pipeline] Clarification needed | ticker={state.ticker} | "
            f"candidates={[c.get('ticker') for c in state.disambiguation_candidates]}"
        )
        return _build_clarification_result(state, start_time)

    # ─── Step 2: Handle response_type ─────────────────────────
    response_type = state.execution_plan.response_type

    if response_type == ResponseType.CHAT:
        if prior_state and prior_state.has_existing_dashboard:
            # Inject prior agent outputs into current state
            # so Synthesizer has full context to answer from
            state.quantitative_result  = prior_state.quantitative_result
            state.qualitative_result   = prior_state.qualitative_result
            state.risk_governance_result = prior_state.risk_governance_result
            state.sentiment_result     = prior_state.sentiment_result
            state.has_existing_dashboard = True
            state.synthesis            = prior_state.synthesis
            logger.info(
                f"[pipeline] CHAT mode — prior state loaded from session "
                f"{resolved_session_id}. Skipping agents."
            )
            state = await run_synthesizer(state)
        else:
            logger.warning(
                "[pipeline] CHAT requested but no prior dashboard in session. "
                "Falling back to dashboard mode."
            )
            state.execution_plan.response_type = ResponseType.DASHBOARD
            response_type = ResponseType.DASHBOARD
            state = await run_pipeline(state)

    elif response_type == ResponseType.PATCH:
        # Check hash — if frontend state is stale, do full dashboard
        if prior_state and not _check_state_hash(prior_state, existing_state_hash):
            logger.warning(
                "[pipeline] State hash mismatch on PATCH. "
                "Returning full dashboard refresh."
            )
            state.execution_plan.response_type = ResponseType.DASHBOARD
            response_type = ResponseType.DASHBOARD
            state = await run_pipeline(state)
        else:
            if prior_state:
                state.quantitative_result    = prior_state.quantitative_result
                state.qualitative_result     = prior_state.qualitative_result
                state.risk_governance_result = prior_state.risk_governance_result
                state.sentiment_result       = prior_state.sentiment_result
                state.synthesis              = prior_state.synthesis
                state.has_existing_dashboard = True
            state = await run_pipeline(state)

    else:  # DASHBOARD
        state = await run_pipeline(state)

    # ── Set has_existing_dashboard after successful dashboard/patch ──
    if response_type in (ResponseType.DASHBOARD, ResponseType.PATCH):
        state.has_existing_dashboard = True

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"[pipeline] ===== Done: {state.ticker} in {elapsed:.1f}s | "
        f"verdict={state.investment_verdict} ====="
    )

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
