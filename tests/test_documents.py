"""Unit tests for document service: markdown generation and saving."""
import pytest

from backend.services.documents import build_markdown, save_markdown


def test_build_markdown():
    sections = [
        {"heading": "Intro", "body": "This is an introductory section."},
        {"heading": "Metrics", "bullets": ["Metric A: 100", "Metric B: 200"]},
        {
            "heading": "Data Table",
            "table": {
                "columns": ["Col 1", "Col 2"],
                "rows": [["Val 1", "Val 2"], ["Val 3", "Val 4"]],
            },
        },
    ]
    md = build_markdown("Test Report", sections, metadata={"author": "Unit Test"})
    assert "# Test Report" in md
    assert "author: Unit Test" in md
    assert "## Intro" in md
    assert "This is an introductory section." in md
    assert "- Metric A: 100" in md
    assert "| Col 1 | Col 2 |" in md


def test_save_markdown():
    res = save_markdown("test_run_123", "# Title\n\nContent here.")
    assert "reports/test_run_123.md" in res["path"]
    assert res["bytes"] > 0


def test_save_markdown_invalid_id():
    with pytest.raises(ValueError):
        save_markdown("../sneaky_path", "Content")
