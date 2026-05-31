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

    async def route_query(self, request: QueryRequest) -> RoutingDecision:
        """
        Determine the optimal retrieval strategy for a query.

        Args:
            request: The user query, optionally with some pre-filled filters.

        Returns:
            RoutingDecision containing the tier and merged metadata filters.
        """
        # Call LLM to classify query
        prompt_text = _PROMPT_TEMPLATE.render(query=request.query)

        try:
            response = await self.llm.ainvoke(prompt_text)
            parsed_response = self._parse_response(response.content)
            logger.info(
                f"Query routed to {parsed_response.tier}: "
                f"'{request.query[:50]}...'"
            )
        except Exception as e:
            logger.warning(
                f"Query routing failed: {e}. Defaulting to T2 (Hybrid)."
            )
            parsed_response = QueryRouterResponse(
                tier="T2",
                explanation=f"Fallback due to routing error: {e}",
            )

        # Merge extracted filters with explicit filters from the request
        filters = self._merge_filters(request, parsed_response)

        # Map tier to specific retrieval strategy
        strategy = self._map_tier_to_strategy(QueryTier(parsed_response.tier))

        return RoutingDecision(
            tier=QueryTier(parsed_response.tier),
            metadata_filters=filters,
            retrieval_strategy=strategy,
            explanation=parsed_response.explanation,
        )

    # ─── Internal Methods ───────────────────────────────────

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

        return QueryRouterResponse(
            tier=tier,
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
