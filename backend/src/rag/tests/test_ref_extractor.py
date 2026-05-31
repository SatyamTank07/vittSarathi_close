"""
Unit tests for the Reference Extractor.
Tests the regex patterns for finding footnotes and the logic for resolving them.
"""

import pytest

from src.rag.ingestion.ref_extractor import RefExtractor
from src.rag.models.schemas import TableData, ClassifiedSection, ContentBlock


@pytest.fixture
def extractor():
    return RefExtractor()


def test_footnote_extraction(extractor):
    """Test extracting various footnote patterns from table cells."""
    table = TableData(
        headers=[["Assets", "Amount", "Ref"]],
        rows=[
            ["Cash", "100", "Note 5"],
            ["Inventory", "200", "(1)"],
            ["Fixed Assets", "500", "Refer Schedule V"],
            ["Other", "50", "***"],
            ["Debt", "300", "See Note 12"]
        ]
    )
    
    refs = extractor.extract_refs_from_table(table, page_number=1)
    ref_codes = [r.ref_code for r in refs]
    
    assert "Note 5" in ref_codes
    assert "(1)" in ref_codes
    assert "Schedule V" in ref_codes
    assert "***" in ref_codes
    assert "Note 12" in ref_codes


def test_ref_resolution_by_path(extractor):
    """Test resolving a reference by matching the section path."""
    # Raw ref extracted from a table
    class DummyRef:
        ref_code = "Note 5"
        source_table_id = "table_1"
        
    # The section it should point to
    target_section = ClassifiedSection(
        section_type="note_to_accounts",
        section_path=["Notes to Financial Statements", "Note 5 - Property, Plant and Equipment"],
        content_markdown="Details of property, plant, and equipment..."
    )
    
    other_section = ClassifiedSection(
        section_type="note_to_accounts",
        section_path=["Notes to Financial Statements", "Note 6 - Intangible Assets"]
    )
    
    sections = [other_section, target_section]
    
    resolved = extractor.resolve_refs([DummyRef()], sections)
    
    assert len(resolved) == 1
    assert resolved[0].ref_code == "Note 5"
    assert "Details of property" in resolved[0].resolved_text


def test_ref_resolution_schedule(extractor):
    """Test resolving a schedule reference."""
    class DummyRef:
        ref_code = "Schedule V"
        source_table_id = "table_1"
        
    target_section = ClassifiedSection(
        section_type="schedule",
        section_path=["Schedules", "Schedule V: Related Party Disclosures"],
        content_markdown="Related party transactions..."
    )
    
    resolved = extractor.resolve_refs([DummyRef()], [target_section])
    
    assert len(resolved) == 1
    assert resolved[0].ref_code == "Schedule V"
