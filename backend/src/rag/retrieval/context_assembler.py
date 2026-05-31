"""
Context Assembler — final context window builder.

Takes the reranked chunks and builds a clean, token-optimized context
package to feed into the final LLM answering phase. Critically, it
resolves footnote references (e.g. Note 5) found in retrieved tables
and appends their content automatically (T3 queries).
"""

import logging
import uuid
import tiktoken
from typing import Any

from src.rag.models.schemas import RetrievedContext, QueryTier
from src.rag.storage.ref_store import RefStore
from src.rag.storage.document_store import DocumentStore

logger = logging.getLogger("vittsarathi.rag.retrieval.context_assembler")


class ContextAssembler:
    """
    Assembles final LLM context from retrieved chunks and resolves references.
    """

    def __init__(self, ref_store: RefStore, document_store: DocumentStore):
        self.ref_store = ref_store
        self.document_store = document_store
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")

    def assemble(
        self, 
        retrieved_context: RetrievedContext, 
        max_tokens: int = 25000
    ) -> RetrievedContext:
        """
        Enrich the context with resolved references and calculate token usage.
        
        Args:
            retrieved_context: The basic context from HybridRetriever
            max_tokens: The token budget for the context window
            
        Returns:
            Enriched RetrievedContext ready for the final LLM
        """
        logger.info(f"Assembling context for tier {retrieved_context.query_tier.value}")
        
        # Enforce token limit (drop lowest ranked chunks if needed)
        chunks = retrieved_context.chunks
        optimized_chunks = []
        current_tokens = 0
        
        for chunk in chunks:
            # Estimate tokens: metadata prefix + chunk text
            chunk_str = f"[{chunk.metadata.company_id} | {chunk.metadata.fiscal_year} | {chunk.metadata.section_type}]\n{chunk.chunk_text}"
            tokens = len(self.tokenizer.encode(chunk_str))
            
            if current_tokens + tokens > max_tokens:
                logger.debug(f"Token limit reached, dropping {len(chunks) - len(optimized_chunks)} chunks")
                break
                
            optimized_chunks.append(chunk)
            current_tokens += tokens
            
        retrieved_context.chunks = optimized_chunks
        
        # For T3 queries (Cross-Reference) or if chunks contain tables,
        # fetch the actual footnote texts
        if retrieved_context.query_tier == QueryTier.T3_CROSS_REFERENCE or any(c.metadata.content_type == "table" for c in optimized_chunks):
            self._resolve_references(retrieved_context)
            
        # Calculate final tokens
        total_tokens = current_tokens
        for ref in retrieved_context.resolved_refs:
            ref_str = f"{ref['ref_code']}: {ref['resolved_text']}"
            total_tokens += len(self.tokenizer.encode(ref_str))
            
        retrieved_context.total_tokens_estimate = total_tokens
        
        return retrieved_context
        
    def _resolve_references(self, context: RetrievedContext) -> None:
        """
        Scan chunks for structured tables, find their source table IDs,
        and fetch any resolved footnote text to append to the context.
        """
        resolved_refs: list[dict[str, Any]] = []
        seen_refs: set[str] = set()
        
        # We need to map chunk section IDs to table IDs
        # Since chunks correspond to sections, we fetch all tables for the section
        for chunk in context.chunks:
            if chunk.metadata.section_id:
                try:
                    tables = self.document_store.get_tables_for_section(chunk.metadata.section_id)
                    
                    for table in tables:
                        # Get resolved references for this table
                        refs = self.ref_store.get_refs_for_table(table.id)
                        
                        for ref in refs:
                            ref_key = f"{ref.document_id}_{ref.ref_code}"
                            if ref_key not in seen_refs:
                                seen_refs.add(ref_key)
                                resolved_refs.append({
                                    "ref_code": ref.ref_code,
                                    "resolved_text": ref.resolved_text,
                                    "source": f"Table in {chunk.metadata.section_type}"
                                })
                except Exception as e:
                    logger.warning(f"Failed to fetch refs for section {chunk.metadata.section_id}: {e}")
                    
        if resolved_refs:
            logger.info(f"Resolved {len(resolved_refs)} footnote references for context")
            
        context.resolved_refs = resolved_refs
