"""Regression guard for the node->record filepath mapping in vault_embed.

vault_graph.py serialises each Node dataclass via asdict(), which stores the
vault-relative path under the key ``path`` (NOT ``filepath``). vault_embed.py
must read that key so the ``filepath`` column in vault-embeddings.db is
populated; otherwise kbai/retrieve/dense.py emits empty seed filepaths.
"""

import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_vault_root))

from vault_embed import node_filepath  # noqa: E402


def test_reads_path_key():
    """Graph nodes use the `path` key; node_filepath must read it."""
    node = {"id": "n", "path": "00-Captures/cycle of suffering.md", "summary": "s"}
    assert node_filepath(node) == "00-Captures/cycle of suffering.md"


def test_does_not_silently_drop_path():
    """The old bug read n.get('filepath', '') and always returned ''."""
    node = {"id": "n", "path": "06-Maps/some map.md"}
    assert node_filepath(node) != ""


def test_falls_back_to_filepath_key():
    """Graceful fallback for alternate dumps that use `filepath`."""
    node = {"id": "n", "filepath": "01-Ideas/legacy.md"}
    assert node_filepath(node) == "01-Ideas/legacy.md"


def test_prefers_path_over_filepath_when_both_present():
    node = {"id": "n", "path": "canonical.md", "filepath": "legacy.md"}
    assert node_filepath(node) == "canonical.md"


def test_returns_empty_string_when_neither_present():
    assert node_filepath({"id": "n"}) == ""
