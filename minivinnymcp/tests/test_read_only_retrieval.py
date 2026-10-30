"""Reading the vault must not write to the index: that database sits in iCloud,
and test runs were filling it with fake usage data."""

import os
import sys
from pathlib import Path

import pytest

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

import minivinnymcp.server as mv  # noqa: E402


@pytest.mark.parametrize(
    "call",
    [
        lambda: mv._assemble_context_impl("governance capital", 3, 2000, "standard"),
        lambda: mv.council_retrieve("governance capital", top_k=3),
    ],
    ids=["assemble", "council"],
)
def test_retrieval_leaves_the_index_untouched(call):
    if not mv._DB_PATH.exists() or not mv._GRAPH_PATH.exists():
        pytest.skip("needs the built index")
    before = mv._DB_PATH.stat().st_mtime_ns
    call()
    assert mv._DB_PATH.stat().st_mtime_ns == before
