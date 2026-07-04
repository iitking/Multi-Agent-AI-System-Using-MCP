"""Unit tests for research documents search and untrusted snippet handling."""
import pytest

from backend.services.research import list_documents, search_documents


def test_list_documents():
    res = list_documents()
    docs = res.get("documents", [])
    assert len(docs) >= 2
    names = {d["name"] for d in docs}
    assert "2025-q4-west-distribution-incident.md" in names
    assert "2025-q3-aurora-laptop-market-update.md" in names


def test_search_documents():
    res = search_documents("distribution center outage", limit=2)
    assert len(res["results"]) > 0
    top_hit = res["results"][0]
    assert "west-distribution" in top_hit["source"]
    assert top_hit["score"] > 0
    assert top_hit["flagged"] is False


def test_search_documents_empty_query():
    with pytest.raises(ValueError):
        search_documents("")
