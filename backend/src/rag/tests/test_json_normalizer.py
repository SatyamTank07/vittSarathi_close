"""
Unit tests for the JSON Normalizer.
Tests the fallback paths for extracting data from unpredictable Sarvam JSON structures.
"""

import pytest

from src.rag.ingestion.json_normalizer import JsonNormalizer
from src.rag.models.schemas import NormalizedPage


@pytest.fixture
def normalizer():
    return JsonNormalizer()


def test_empty_input(normalizer):
    """Test handling of completely empty input."""
    page = normalizer.normalize({}, page_number=1)
    assert isinstance(page, NormalizedPage)
    assert page.page_number == 1
    assert len(page.content_blocks) == 0


def test_standard_blocks_list(normalizer):
    """Test standard extraction from raw['blocks']."""
    raw = {
        "blocks": [
            {"type": "heading", "level": 2, "text": "Financial Highlights"},
            {"type": "text", "text": "Revenue grew by 15%."},
        ]
    }
    page = normalizer.normalize(raw, page_number=1)
    assert len(page.content_blocks) == 2
    assert page.content_blocks[0].block_type == "heading"
    assert page.content_blocks[0].heading_level == 2
    assert page.content_blocks[0].content_text == "Financial Highlights"
    
    assert page.content_blocks[1].block_type == "text"
    assert page.content_blocks[1].content_text == "Revenue grew by 15%."


def test_alternative_blocks_path(normalizer):
    """Test extraction from alternative path raw['content']['elements']."""
    raw = {
        "content": {
            "elements": [
                {"element_type": "paragraph", "value": "Test paragraph."}
            ]
        }
    }
    page = normalizer.normalize(raw, page_number=1)
    assert len(page.content_blocks) == 1
    assert page.content_blocks[0].block_type == "text"
    assert page.content_blocks[0].content_text == "Test paragraph."


def test_table_extraction_complex(normalizer):
    """Test extraction of a complex table structure."""
    raw = {
        "blocks": [
            {
                "type": "table",
                "table_data": {
                    "headers": [["Year", "Revenue", "Note"]],
                    "rows": [
                        [{"text": "2023"}, {"text": "100"}, {"text": "(1)"}],
                        [{"text": "2024"}, {"text": "120"}, {"text": "Note 2"}]
                    ]
                }
            }
        ]
    }
    page = normalizer.normalize(raw, page_number=1)
    assert len(page.content_blocks) == 1
    
    block = page.content_blocks[0]
    assert block.block_type == "table"
    assert block.table_data is not None
    
    table = block.table_data
    assert table.num_rows == 2
    assert table.num_columns == 3
    assert table.headers == [["Year", "Revenue", "Note"]]
    assert table.rows[0] == ["2023", "100", "(1)"]
    assert table.rows[1] == ["2024", "120", "Note 2"]
    
    # Check that footnote extraction happened during normalization
    assert "(1)" in table.footnotes
    assert "Note 2" in table.footnotes


def test_html_fallback(normalizer):
    """Test falling back to HTML parsing when JSON is empty."""
    html = """
    <h1>Title</h1>
    <p>Some text.</p>
    <table>
        <tr><th>Col1</th><th>Col2</th></tr>
        <tr><td>Val1</td><td>Val2</td></tr>
    </table>
    """
    page = normalizer.normalize({}, page_number=1, raw_html=html)
    
    assert len(page.content_blocks) == 2
    
    # First block is the table (HTML fallback extracts tables first)
    assert page.content_blocks[0].block_type == "table"
    assert page.content_blocks[0].table_data.headers == [["Col1", "Col2"]]
    assert page.content_blocks[0].table_data.rows == [["Val1", "Val2"]]
    
    # Second block is the remaining text
    assert page.content_blocks[1].block_type == "text"
    assert "Title Some text." in page.content_blocks[1].content_text
