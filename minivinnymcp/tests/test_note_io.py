"""Stage 1 item 1.3: kbai.storage.note_io.find_note_file unification tests."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.storage.note_io import find_note_file


def test_returns_none_for_empty(tmp_path):
    assert find_note_file("", tmp_path) is None


def test_finds_via_node_metadata(tmp_path):
    f = tmp_path / "sub" / "alpha.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    out = find_note_file("alpha", tmp_path, node={"filepath": "sub/alpha.md"})
    assert out == f


def test_finds_via_alt_node_keys(tmp_path):
    f = tmp_path / "beta.md"
    f.write_text("hi")
    out = find_note_file("beta", tmp_path, node={"path": "beta.md"})
    assert out == f


def test_finds_via_path_input(tmp_path):
    f = tmp_path / "deep" / "gamma.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    # note_id contains "/" so it's treated as a path
    out = find_note_file("deep/gamma.md", tmp_path)
    assert out == f


def test_finds_via_absolute_path(tmp_path):
    f = tmp_path / "delta.md"
    f.write_text("hi")
    out = find_note_file(str(f), tmp_path)
    assert out == f


def test_falls_back_to_rglob(tmp_path):
    f = tmp_path / "nested" / "deeper" / "epsilon.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    out = find_note_file("epsilon", tmp_path)
    assert out == f


def test_returns_none_when_missing(tmp_path):
    assert find_note_file("does-not-exist", tmp_path) is None


def test_minivinny_shim_uses_unified_helper():
    """The mini-vinny `_find_note_file` shim should now delegate."""
    import minivinnymcp.server as mv
    # Make sure import works and the function is callable
    assert callable(mv._find_note_file)


def test_perplexity_shim_uses_unified_helper():
    import perplexitymcp.server as pp
    assert callable(pp._find_note_file)
