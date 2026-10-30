import pytest

from minivinnymcp.server import retrieve_search

pytestmark = pytest.mark.live

REQUIRED_KEYS = {"note_id", "title", "summary", "score", "filepath"}


def test_returns_list_with_results():
    results = retrieve_search("governance capital")
    assert isinstance(results, list)
    assert len(results) >= 1


def test_result_shape():
    results = retrieve_search("governance capital", top_k=3)
    for item in results:
        assert REQUIRED_KEYS <= item.keys()
