"""
Query Router — LLM-based 4-tier query classifier.

Routes user queries into one of four tiers:
    T1 (Fact Lookup):       Tree navigation (PageIndex)
    T2 (Multi-Section):     Parallel PageIndex + Vector
    T3 (Cross-Reference):   Tree + Ref Resolution
    T4 (Temporal Synthesis): Vector across multiple documents

Extracts metadata filters (company, year, sections) to narrow search scope.
Uses gpt-4o-mini with structured output for cost efficiency.
"""

import json
import logging
import os
from pathlib import Path

from jinja2 import Template
from langchain_openai import ChatOpenAI

from src.rag.config import (
    CLASSIFIER_MODEL,
    CLASSIFIER_MAX_TOKENS,
    CLASSIFIER_TEMPERATURE,
    PROMPTS_DIR,
    SECTION_TYPES,
)
from src.rag.models.schemas import (
    MetadataFilter,
    QueryRequest,
    QueryRouterResponse,
    QueryTier,
    RoutingDecision,
)

# Confidence threshold — below this, keyword fallback is checked
CONFIDENCE_THRESHOLD = 0.7

# Keywords that strongly signal a T1 structured table lookup
T1_TABLE_KEYWORDS = {
    "balance sheet", "profit and loss", "p&l", "eps",
    "earnings per share", "cash flow statement", "total assets",
    "total liabilities", "net worth", "shareholders equity",
    "revenue from operations", "ebitda", "net profit", "pat",
    "gross block", "depreciation", "retained earnings",
}

logger = logging.getLogger("vittsarathi.rag.retrieval.query_router")

# Load prompt template
_PROMPT_PATH = PROMPTS_DIR / "query_router.jinja2"
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _PROMPT_TEMPLATE = Template(f.read())


class QueryRouter:
    """
    Classifies user queries into retrieval tiers and extracts metadata filters.

    Usage:
        router = QueryRouter()
        decision = await router.route_query(QueryRequest(query="..."))
    """

    def __init__(self, model: str = CLASSIFIER_MODEL):
        api_key = os.environ.get("OPENAI_API_KEY", "")
        api_key = api_key.strip('"').strip("'")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

        self.llm = ChatOpenAI(
            model=model,
            temperature=CLASSIFIER_TEMPERATURE,
            max_tokens=CLASSIFIER_MAX_TOKENS,
            api_key=api_key,
        )

    async def route_query(self, request: QueryRequest, db_session=None) -> RoutingDecision:
        """
        Determine the optimal retrieval strategy for a query using two-pass routing.

        Args:
            request: The user query, optionally with some pre-filled filters.
            db_session: Optional DB session for dynamic section discovery.

        Returns:
            RoutingDecision containing the tier and merged metadata filters.
        """
        # --- PASS 1: Extract Entities ---
        entities = await self._pass1_extract_entities(request.query)
        
        # Merge request filters with pass 1 filters for DB lookup
        comp_id = request.company_id or entities.get("company_id")
        yr = request.fiscal_year or entities.get("fiscal_year")
        yrs = entities.get("fiscal_years")
        
        # --- DB LOOKUP: Get Available Sections ---
        available_sections = self._get_available_sections(comp_id, yr, yrs, db_session)
        sections_str = ", ".join(available_sections)
        logger.info(f"Pass 1 extracted: {comp_id} | {yr}. Available sections: {sections_str}")

        # --- PASS 2: Full Routing with Dynamic Taxonomy ---
        prompt_text = _PROMPT_TEMPLATE.render(query=request.query, available_sections=sections_str)

        fallback_applied = False
        fallback_reason = None

        try:
            response = await self.llm.ainvoke(prompt_text)
            parsed_response = self._parse_response(response.content)
            logger.info(
                f"Query routed to {parsed_response.tier}: "
                f"'{request.query[:50]}...'"
            )
            
            # ── Confidence threshold + T1 keyword fallback ──────────────
            if parsed_response.confidence < CONFIDENCE_THRESHOLD:
                query_lower = request.query.lower()
                keyword_hit = next(
                    (kw for kw in T1_TABLE_KEYWORDS if kw in query_lower),
                    None
                )
                if keyword_hit:
                    original_tier = parsed_response.tier
                    parsed_response.tier = "T1"
                    fallback_applied = True
                    fallback_reason = (
                        f"Confidence {parsed_response.confidence:.2f} below threshold "
                        f"{CONFIDENCE_THRESHOLD}. Keyword '{keyword_hit}' matched. "
                        f"Overriding {original_tier} → T1."
                    )
                    logger.warning(
                        f"[QueryRouter] Low confidence fallback: {fallback_reason}"
                    )
                else:
                    logger.info(
                        f"[QueryRouter] Low confidence ({parsed_response.confidence:.2f}) "
                        f"but no T1 keyword match. Keeping tier {parsed_response.tier}."
                    )
        except Exception as e:
            logger.warning(
                f"Query routing failed: {e}. Defaulting to T2 (Hybrid)."
            )
            parsed_response = QueryRouterResponse(
                tier="T2",
                confidence=0.0,
                explanation=f"Fallback due to routing error: {e}",
            )
            fallback_applied = True
            fallback_reason = f"Router exception: {e}"

        # Merge extracted filters with explicit filters from the request
        filters = self._merge_filters(request, parsed_response)

        # Map tier to specific retrieval strategy
        strategy = self._map_tier_to_strategy(QueryTier(parsed_response.tier))

        return RoutingDecision(
            tier=QueryTier(parsed_response.tier),
            confidence=parsed_response.confidence,
            fallback_applied=fallback_applied,
            metadata_filters=filters,
            retrieval_strategy=strategy,
            explanation=parsed_response.explanation,
        )

    # ─── Internal Methods ───────────────────────────────────

    async def _pass1_extract_entities(self, query: str) -> dict:
        """Fast pass to extract only company_id and fiscal_year(s)."""
        prompt = f"""Extract the company name and fiscal year(s) from the query.
Respond ONLY with valid JSON:
{{
  "company_id": "Company name or ticker",
  "fiscal_year": 2024,
  "fiscal_years": [2023, 2024]
}}
If not found, use null.
Query: {query}"""
        try:
            response = await self.llm.ainvoke(prompt)
            text = response.content.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines).strip()
            import re
            match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"company_id": None, "fiscal_year": None, "fiscal_years": None}
        except Exception as e:
            logger.warning(f"Pass 1 extraction failed: {e}")
            return {"company_id": None, "fiscal_year": None, "fiscal_years": None}

    def _get_available_sections(self, company_id, year, years, db_session) -> list[str]:
        """Query the DB for unique section types for this company/year."""
        if not db_session or not company_id:
            return SECTION_TYPES
            
        from src.rag.storage.document_store import DocumentStore
        from src.rag.models.database import RAGPageIndexNode, RAGSectionChunk
        
        doc_store = DocumentStore(db_session)
        docs = doc_store.find_documents(
            company_id=company_id,
            fiscal_year=year,
            fiscal_years=years
        )
        
        if not docs:
            return SECTION_TYPES
            
        doc_ids = [doc.id for doc in docs]
        sections = set()
        
        # Get from PageIndex
        page_nodes = db_session.query(RAGPageIndexNode).filter(RAGPageIndexNode.document_id.in_(doc_ids)).all()
        for n in page_nodes:
            if n.tree_json and 'section_type' in n.tree_json:
                sections.add(n.tree_json['section_type'])
                
        # Get from VectorChunks
        from sqlalchemy import text
        for doc_id in doc_ids:
            res = db_session.execute(text("SELECT DISTINCT metadata->>'section_type' FROM rag_section_chunks WHERE metadata->>'document_id' = :did"), {"did": str(doc_id)})
            for row in res:
                if row[0]:
                    sections.add(row[0])
                    
        if not sections:
            return SECTION_TYPES
            
        return list(sections)

    def _parse_response(self, raw_text: str) -> QueryRouterResponse:
        """Parse LLM response into structured output."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError("Could not parse JSON from routing response")

        # Validate tier
        tier = data.get("tier", "T2")
        if tier not in ("T1", "T2", "T3", "T4"):
            tier = "T2"

        # Validate sections against taxonomy
        sections = data.get("section_types")
        if sections:
            sections = [s for s in sections if s in SECTION_TYPES]

        confidence = float(data.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))   # clamp to [0.0, 1.0]

        return QueryRouterResponse(
            tier=tier,
            confidence=confidence,
            company_id=data.get("company_id"),
            fiscal_year=data.get("fiscal_year"),
            fiscal_years=data.get("fiscal_years"),
            section_types=sections,
            explanation=data.get("explanation", ""),
        )

    def _merge_filters(
        self, request: QueryRequest, response: QueryRouterResponse
    ) -> MetadataFilter:
        """
        Merge explicitly provided filters (from request) with
        implicit filters (extracted by LLM). Explicit wins.
        """
        filters = MetadataFilter()

        # Company ID
        if request.company_id:
            filters.company_id = request.company_id
        elif response.company_id:
            filters.company_id = response.company_id

        # Fiscal Year
        if request.fiscal_year:
            filters.fiscal_year = request.fiscal_year
        elif response.fiscal_year:
            filters.fiscal_year = response.fiscal_year

        # Multi-Year (T4 queries)
        if response.fiscal_years and not filters.fiscal_year:
            filters.fiscal_years = response.fiscal_years

        # Quarter
        if request.fiscal_quarter:
            filters.fiscal_quarter = request.fiscal_quarter

        # Sections
        if request.section_types:
            filters.section_types = request.section_types
        elif response.section_types:
            filters.section_types = response.section_types

        return filters

    def _map_tier_to_strategy(self, tier: QueryTier) -> str:
        """Map the 4 complexity tiers to specific retrieval strategies."""
        mapping = {
            QueryTier.T1_FACT_LOOKUP: "pageindex_tree",
            QueryTier.T2_MULTI_SECTION: "hybrid",
            QueryTier.T3_CROSS_REFERENCE: "pageindex_refs",
            QueryTier.T4_TEMPORAL_SYNTHESIS: "vector_multi_doc",
        }
        return mapping[tier]

def log_routing_decision(
    db_session,
    query: str,
    decision: RoutingDecision,
    fallback_reason: str | None = None,
    routing_error: str | None = None,
) -> None:
    """
    Persists a routing decision to rag_router_log.
    Called fire-and-forget from HybridRetriever.
    Never raises — logging must never break the retrieval path.
    """
    try:
        from src.rag.models.database import RAGRouterLog
        log_entry = RAGRouterLog(
            query_text=query,
            assigned_tier=decision.tier.value,
            confidence=int(decision.confidence * 100),  # store as 0-100 int
            fallback_applied=1 if decision.fallback_applied else 0,
            fallback_reason=fallback_reason,
            company_id=decision.metadata_filters.company_id,
            fiscal_year=decision.metadata_filters.fiscal_year,
            section_types=decision.metadata_filters.section_types,
            explanation=decision.explanation,
            routing_error=routing_error,
        )
        db_session.add(log_entry)
        db_session.commit()
    except Exception as e:
        logger.error(f"[QueryRouter] Failed to log routing decision: {e}")
