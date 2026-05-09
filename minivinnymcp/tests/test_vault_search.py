import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from minivinnymcp.server import vault_search

REQUIRED_KEYS = {"note_id", "title", "summary", "score", "filepath"}


def test_returns_list_with_results():
    results = vault_search("governance capital")
    assert isinstance(results, list)
    assert len(results) >= 1


def test_result_shape():
    results = vault_search("governance capital", top_k=3)
    for item in results:
        assert REQUIRED_KEYS <= item.keys()
